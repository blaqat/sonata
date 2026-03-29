from __future__ import annotations

import asyncio
import contextlib
import html
import json
import secrets
import time
import urllib.parse
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from modules.utils import async_cprint


CURRENT_IO: ContextVar["TerminalIO | None"] = ContextVar("term_console_io", default=None)


@dataclass
class PendingPrompt:
    prompt_id: str
    text: str
    editable: bool
    current: str | None
    future: asyncio.Future[str]


class TerminalIO:
    session_id: str
    label: str

    async def prompt(
        self,
        text,
        convert=None,
        exit_if=None,
        exit_msg=None,
        color=None,
        exit_callback: Callable | None = None,
    ):
        raise NotImplementedError

    async def editable_prompt(
        self,
        text: str,
        current: str,
        convert=None,
        exit_if=None,
        exit_msg=None,
        color=None,
        exit_callback: Callable | None = None,
    ):
        raise NotImplementedError


class TerminalConsole:
    def __init__(self, history_limit: int = 400):
        self.history_limit = history_limit
        self.history: deque[dict[str, Any]] = deque(maxlen=history_limit)
        self.listeners: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self.controller_id: str | None = None
        self.pending_prompts: dict[str, PendingPrompt] = {}
        self.command_lock = asyncio.Lock()
        self.command_owner: str | None = None
        self.seq = 0

    def subscribe(self) -> tuple[str, asyncio.Queue[dict[str, Any]]]:
        listener_id = secrets.token_urlsafe(8)
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.listeners[listener_id] = queue
        return listener_id, queue

    def unsubscribe(self, listener_id: str):
        self.listeners.pop(listener_id, None)

    def snapshot_for(self, session_id: str) -> dict[str, Any]:
        return {
            "type": "snapshot",
            "session_id": session_id,
            "history": list(self.history),
            "controller_id": self.controller_id,
            "is_controller": self.controller_id == session_id,
            "busy": self.command_lock.locked(),
            "pending_prompt": self._prompt_payload(self.pending_prompts.get(session_id)),
        }

    def _prompt_payload(self, pending: PendingPrompt | None) -> dict[str, Any] | None:
        if pending is None:
            return None
        return {
            "prompt_id": pending.prompt_id,
            "text": pending.text,
            "editable": pending.editable,
            "current": pending.current,
        }

    async def publish(self, event_type: str, **payload):
        event = {
            "seq": self.seq,
            "timestamp": time.time(),
            "type": event_type,
            **payload,
        }
        self.seq += 1
        self.history.append(event)
        stale: list[str] = []
        for listener_id, queue in self.listeners.items():
            try:
                queue.put_nowait(event)
            except Exception:
                stale.append(listener_id)
        for listener_id in stale:
            self.listeners.pop(listener_id, None)

    async def set_controller(self, session_id: str, force: bool = False) -> tuple[bool, str]:
        if self.controller_id is None or self.controller_id == session_id:
            self.controller_id = session_id
            await self.publish("controller", controller_id=self.controller_id)
            return True, "Control granted."
        if not force:
            return False, "Another session currently has control."
        self.controller_id = session_id
        await self.publish("controller", controller_id=self.controller_id)
        return True, "Control taken over."

    async def release_controller(self, session_id: str) -> tuple[bool, str]:
        if self.controller_id != session_id:
            return False, "Only the active controller can release control."
        self.controller_id = None
        await self.publish("controller", controller_id=None)
        return True, "Control released."

    async def force_release(self, session_id: str):
        if self.controller_id != session_id:
            return
        self.controller_id = None
        pending = self.pending_prompts.pop(session_id, None)
        if pending is not None and not pending.future.done():
            pending.future.cancel()
        await self.publish("controller", controller_id=None)

    async def clear_all_sessions(self):
        controller_id = self.controller_id
        self.controller_id = None
        for pending in self.pending_prompts.values():
            if not pending.future.done():
                pending.future.cancel()
        self.pending_prompts.clear()
        if controller_id is not None:
            await self.publish("controller", controller_id=None)

    async def submit_prompt_response(
        self, session_id: str, prompt_id: str, value: str
    ) -> tuple[bool, str]:
        pending = self.pending_prompts.get(session_id)
        if pending is None or pending.prompt_id != prompt_id:
            return False, "No matching prompt is waiting for input."
        if pending.future.done():
            return False, "Prompt already resolved."
        pending.future.set_result(value)
        return True, "Prompt input accepted."

    async def cancel_prompt(
        self, session_id: str, prompt_id: str | None = None
    ) -> tuple[bool, str]:
        pending = self.pending_prompts.get(session_id)
        if pending is None:
            return False, "No prompt is waiting for input."
        if prompt_id is not None and pending.prompt_id != prompt_id:
            return False, "No matching prompt is waiting for input."
        if pending.future.done():
            return False, "Prompt already resolved."
        pending.future.set_result("exit")
        return True, "Prompt exited."

    async def request_prompt(
        self,
        session_id: str,
        text: str,
        editable: bool = False,
        current: str | None = None,
    ) -> str:
        if self.controller_id != session_id:
            raise RuntimeError("Only the active controller can answer prompts.")
        prompt_id = secrets.token_urlsafe(8)
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        pending = PendingPrompt(
            prompt_id=prompt_id,
            text=text,
            editable=editable,
            current=current,
            future=future,
        )
        self.pending_prompts[session_id] = pending
        await self.publish(
            "prompt",
            session_id=session_id,
            prompt=self._prompt_payload(pending),
        )
        try:
            value = await future
            await self.publish(
                "prompt_resolved",
                session_id=session_id,
                prompt_id=prompt_id,
            )
            return value
        finally:
            self.pending_prompts.pop(session_id, None)

    async def emit_output(self, text: str, stream: str = "stdout"):
        await self.publish("output", stream=stream, text=text)

    async def run_command(
        self,
        session_id: str,
        command: str,
        runner: Callable[[], Awaitable[None]],
    ) -> tuple[bool, str]:
        if self.controller_id != session_id:
            return False, "Only the active controller can run commands."
        if self.command_lock.locked():
            return False, "A command is already running."

        async def _wrapped():
            async with self.command_lock:
                self.command_owner = session_id
                await self.publish(
                    "command",
                    phase="start",
                    session_id=session_id,
                    command=command,
                )
                try:
                    await runner()
                except Exception as exc:
                    await self.emit_output(str(exc), stream="stderr")
                finally:
                    self.command_owner = None
                    await self.publish(
                        "command",
                        phase="end",
                        session_id=session_id,
                        command=command,
                    )

        asyncio.create_task(_wrapped())
        return True, "Command accepted."


class WebTerminalIO(TerminalIO):
    def __init__(self, console: TerminalConsole, session_id: str):
        self.console = console
        self.session_id = session_id
        self.label = f"web:{session_id[:6]}"

    async def prompt(
        self,
        text,
        convert=None,
        exit_if=None,
        exit_msg=None,
        color=None,
        exit_callback: Callable | None = None,
    ):
        value = await self.console.request_prompt(self.session_id, str(text))
        return _apply_prompt_rules(value, convert, exit_if, exit_msg, exit_callback)

    async def editable_prompt(
        self,
        text: str,
        current: str,
        convert=None,
        exit_if=None,
        exit_msg=None,
        color=None,
        exit_callback: Callable | None = None,
    ):
        value = await self.console.request_prompt(
            self.session_id,
            str(text),
            editable=True,
            current=current,
        )
        return _apply_prompt_rules(value, convert, exit_if, exit_msg, exit_callback)


def _apply_prompt_rules(value, convert, exit_if, exit_msg, exit_callback):
    from modules.utils import E, async_cprint

    def _emit_prompt_error(message: str):
        async_cprint(message, "red")
        io = CURRENT_IO.get()
        if isinstance(io, WebTerminalIO):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(io.console.emit_output(message, stream="stderr"))
            except RuntimeError:
                pass

    if value == "exit":
        if exit_callback is not None:
            exit_callback()
        raise E
    if convert is not None:
        value = convert(value)
        if value is None:
            _emit_prompt_error(exit_msg or "Invalid conversion")
            raise E
    if exit_if is not None and exit_if(value):
        if exit_msg is not None:
            _emit_prompt_error(exit_msg)
        raise E
    return value


@contextlib.asynccontextmanager
async def bind_terminal_io(io: TerminalIO | None):
    token = CURRENT_IO.set(io)
    try:
        yield
    finally:
        CURRENT_IO.reset(token)


class TermConsoleServer:
    def __init__(
        self,
        console: TerminalConsole,
        command_handler: Callable[[str, str], Awaitable[tuple[bool, str]]],
        secret: str,
        host: str = "0.0.0.0",
        port: int = 8080,
        base_path: str = "/",
    ):
        self.console = console
        self.command_handler = command_handler
        self.secret = secret
        self.host = host
        self.port = port
        self.base_path = _normalize_base_path(base_path)
        self.cookie_name = "term_console_token"
        self.tokens: dict[str, float] = {}
        self.server: asyncio.AbstractServer | None = None

    async def start(self):
        if self.server is not None:
            return
        self.server = await asyncio.start_server(self._handle_client, self.host, self.port)
        self._log(f"listening on {self.host}:{self.port}{self.base_path}")

    async def stop(self):
        if self.server is None:
            return
        self.server.close()
        await self.server.wait_closed()
        self.server = None

    def _log(self, message: str, color: str = "yellow"):
        async_cprint(f"[term-web] {message}", color)

    def is_authenticated(self, headers: dict[str, str]) -> str | None:
        cookies = _parse_cookies(headers.get("cookie", ""))
        token = cookies.get(self.cookie_name)
        if token and token in self.tokens:
            return token
        return None

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        request = None
        try:
            request = await _read_http_request(reader)
            if request is None:
                writer.close()
                await writer.wait_closed()
                return
            self._log(f"{request['method']} {request['path']}")
            response = await self._dispatch(request, writer)
            if response is not None:
                self._log(f"{request['method']} {request['path']} -> {response[0]}")
                await _write_response(writer, *response)
        except Exception:
            if request is not None:
                self._log(f"{request['method']} {request['path']} -> 500", "red")
            with contextlib.suppress(Exception):
                await _write_response(
                    writer,
                    500,
                    {"Content-Type": "text/plain; charset=utf-8"},
                    b"Internal Server Error",
                )
        finally:
            if not writer.is_closing():
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()

    async def _dispatch(self, request: dict[str, Any], writer):
        method = request["method"]
        path = request["path"]
        headers = request["headers"]
        session_id = self.is_authenticated(headers)
        route = _trim_base_path(path, self.base_path)
        if route is None:
            return 404, {"Content-Type": "text/plain; charset=utf-8"}, b"Not Found"

        if method == "GET" and route == "":
            return (
                200,
                {"Content-Type": "text/html; charset=utf-8"},
                _html_page(self.base_path).encode("utf-8"),
            )

        if method == "POST" and route == "/api/login":
            payload = _json_body(request)
            if payload.get("secret") != self.secret:
                self._log("login rejected", "red")
                return (
                    401,
                    {"Content-Type": "application/json"},
                    json.dumps({"ok": False, "message": "Invalid secret."}).encode(),
                )
            token = secrets.token_urlsafe(18)
            self.tokens[token] = time.time()
            self._log("login accepted")
            return (
                200,
                {
                    "Content-Type": "application/json",
                    "Set-Cookie": (
                        f"{self.cookie_name}={token}; HttpOnly; Path={self.base_path}; "
                        "SameSite=Lax"
                    ),
                },
                json.dumps({"ok": True}).encode(),
            )

        if session_id is None:
            return (
                401,
                {"Content-Type": "application/json"},
                json.dumps({"ok": False, "message": "Authentication required."}).encode(),
            )

        if method == "POST" and route == "/api/logout":
            self.tokens.pop(session_id, None)
            await self.console.force_release(session_id)
            self._log(f"logout {session_id[:6]}")
            return (
                200,
                {
                    "Content-Type": "application/json",
                    "Set-Cookie": (
                        f"{self.cookie_name}=deleted; HttpOnly; Path={self.base_path}; "
                        "Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax"
                    ),
                },
                json.dumps({"ok": True}).encode(),
            )

        if method == "GET" and route == "/api/session":
            return (
                200,
                {"Content-Type": "application/json"},
                json.dumps(self.console.snapshot_for(session_id)).encode(),
            )

        if method == "GET" and route == "/api/events":
            return await self._handle_events(session_id, writer)

        if method == "POST" and route == "/api/control":
            payload = _json_body(request)
            action = payload.get("action")
            if action == "acquire":
                ok, message = await self.console.set_controller(session_id, force=False)
            elif action == "takeover":
                ok, message = await self.console.set_controller(session_id, force=True)
            elif action == "release":
                ok, message = await self.console.release_controller(session_id)
            else:
                ok, message = False, "Unknown control action."
            self._log(
                f"control {action} {session_id[:6]} -> {'ok' if ok else 'blocked'}"
            )
            return (
                200 if ok else 409,
                {"Content-Type": "application/json"},
                json.dumps({"ok": ok, "message": message}).encode(),
            )

        if method == "POST" and route == "/api/debug/clear-sessions":
            self.tokens.clear()
            await self.console.clear_all_sessions()
            self._log(f"debug clear sessions by {session_id[:6]}")
            return (
                200,
                {
                    "Content-Type": "application/json",
                    "Set-Cookie": (
                        f"{self.cookie_name}=deleted; HttpOnly; Path={self.base_path}; "
                        "Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax"
                    ),
                },
                json.dumps({"ok": True, "message": "Cleared all sessions."}).encode(),
            )

        if method == "POST" and route == "/api/command":
            payload = _json_body(request)
            command = str(payload.get("command", "")).strip()
            if not command:
                return (
                    400,
                    {"Content-Type": "application/json"},
                    json.dumps({"ok": False, "message": "Command is required."}).encode(),
                )
            ok, message = await self.command_handler(session_id, command)
            self._log(
                f"command {session_id[:6]} `{command}` -> {'ok' if ok else 'blocked'}"
            )
            return (
                200 if ok else 409,
                {"Content-Type": "application/json"},
                json.dumps({"ok": ok, "message": message}).encode(),
            )

        if method == "POST" and route == "/api/prompt":
            payload = _json_body(request)
            ok, message = await self.console.submit_prompt_response(
                session_id,
                str(payload.get("prompt_id", "")),
                str(payload.get("value", "")),
            )
            self._log(f"prompt {session_id[:6]} -> {'ok' if ok else 'blocked'}")
            return (
                200 if ok else 409,
                {"Content-Type": "application/json"},
                json.dumps(
                    {
                        "ok": ok,
                        "message": message,
                        "prompt_active": self.console.pending_prompts.get(session_id)
                        is not None,
                    }
                ).encode(),
            )

        if method == "POST" and route == "/api/prompt/exit":
            payload = _json_body(request)
            raw_prompt_id = payload.get("prompt_id")
            prompt_id = None if raw_prompt_id is None else str(raw_prompt_id)
            ok, message = await self.console.cancel_prompt(session_id, prompt_id)
            self._log(f"prompt-exit {session_id[:6]} -> {'ok' if ok else 'blocked'}")
            return (
                200 if ok else 409,
                {"Content-Type": "application/json"},
                json.dumps(
                    {
                        "ok": ok,
                        "message": message,
                        "prompt_active": self.console.pending_prompts.get(session_id)
                        is not None,
                    }
                ).encode(),
            )

        return 404, {"Content-Type": "text/plain; charset=utf-8"}, b"Not Found"

    async def _handle_events(self, session_id: str, writer):
        listener_id, queue = self.console.subscribe()
        self._log(f"events open {session_id[:6]}")
        headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
        await _write_response(writer, 200, headers, b"", close=False)
        snapshot = self.console.snapshot_for(session_id)
        await _write_sse(writer, snapshot)
        try:
            while True:
                event = await queue.get()
                await _write_sse(writer, event)
        except Exception:
            self._log(f"events closed {session_id[:6]}")
            return None
        finally:
            self.console.unsubscribe(listener_id)


async def _write_sse(writer: asyncio.StreamWriter, event: dict[str, Any]):
    payload = json.dumps(event)
    writer.write(f"data: {payload}\n\n".encode("utf-8"))
    await writer.drain()


async def _write_response(
    writer: asyncio.StreamWriter,
    status: int,
    headers: dict[str, str],
    body: bytes,
    close: bool = True,
):
    reason = {
        200: "OK",
        400: "Bad Request",
        401: "Unauthorized",
        404: "Not Found",
        409: "Conflict",
        500: "Internal Server Error",
    }.get(status, "OK")
    all_headers = dict(headers)
    if close and "Content-Length" not in all_headers:
        all_headers["Content-Length"] = str(len(body))
    if close:
        all_headers.setdefault("Connection", "close")
    writer.write(f"HTTP/1.1 {status} {reason}\r\n".encode("utf-8"))
    for key, value in all_headers.items():
        writer.write(f"{key}: {value}\r\n".encode("utf-8"))
    writer.write(b"\r\n")
    if body:
        writer.write(body)
    await writer.drain()


async def _read_http_request(reader: asyncio.StreamReader) -> dict[str, Any] | None:
    request_line = await reader.readline()
    if not request_line:
        return None
    try:
        method, target, _version = request_line.decode("utf-8").strip().split(" ", 2)
    except ValueError:
        return None
    headers: dict[str, str] = {}
    while True:
        line = await reader.readline()
        if line in {b"\r\n", b"\n", b""}:
            break
        key, value = line.decode("utf-8").split(":", 1)
        headers[key.lower().strip()] = value.strip()
    body = b""
    length = int(headers.get("content-length", "0") or "0")
    if length:
        body = await reader.readexactly(length)
    parsed = urllib.parse.urlsplit(target)
    return {
        "method": method.upper(),
        "path": parsed.path,
        "query": urllib.parse.parse_qs(parsed.query),
        "headers": headers,
        "body": body,
    }


def _parse_cookies(header: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in header.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        cookies[key.strip()] = value.strip()
    return cookies


def _json_body(request: dict[str, Any]) -> dict[str, Any]:
    if not request["body"]:
        return {}
    try:
        return json.loads(request["body"].decode("utf-8"))
    except Exception:
        return {}


def _normalize_base_path(base_path: str) -> str:
    if not base_path:
        return "/"
    if not base_path.startswith("/"):
        base_path = f"/{base_path}"
    if len(base_path) > 1 and base_path.endswith("/"):
        base_path = base_path[:-1]
    return base_path


def _trim_base_path(path: str, base_path: str) -> str | None:
    if base_path == "/":
        return "" if path == "/" else path
    if path == base_path:
        return ""
    if path.startswith(base_path + "/"):
        return path[len(base_path) :]
    return None


def _html_page(base_path: str) -> str:
    safe_base = html.escape(base_path)
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sonata Remote Term</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #fff4ee;
      --panel: #fff9f5;
      --line: #241512;
      --text: #251715;
      --muted: #81666d;
      --yellow: #ffd82b;
      --pink: #ff81b6;
      --purple: #7f49ff;
      --ok: #a6ec9e;
      --danger: #ffb3b3;
      --shadow: 5px 5px 0 var(--line);
      --radius: 24px;
      --radius-sm: 16px;
      --font: "Avenir Next", "Nunito", "Trebuchet MS", sans-serif;
      --mono: "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at top left, rgba(255,129,182,0.22), transparent 28%),
        linear-gradient(180deg, #fffaf6 0%, var(--bg) 100%);
      color: var(--text);
      font-family: var(--font);
    }
    .shell {
      width: min(900px, 100%);
      margin: 0 auto;
      padding: 18px 14px 34px;
    }
    .card {
      background: var(--panel);
      border: 3px solid var(--line);
      border-radius: 28px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .topbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 16px 18px 14px;
      border-bottom: 3px solid var(--line);
      background: linear-gradient(135deg, #ffc9e2 0%, #d4c0ff 100%);
    }
    .title {
      font-size: 15px;
      font-weight: 900;
      text-transform: uppercase;
      letter-spacing: 0.14em;
    }
    .status {
      font-size: 12px;
      color: var(--muted);
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      padding: 10px 14px;
      border: 3px solid var(--line);
      border-radius: 999px;
      box-shadow: 3px 3px 0 var(--line);
      background: #fff;
      font-size: 13px;
      font-weight: 900;
    }
    .status-pill.ok { background: var(--ok); }
    .status-pill.warn { background: var(--danger); }
    .toolbar {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      padding: 14px 18px;
      border-bottom: 3px solid var(--line);
      background: #fff6ef;
    }
    .toolbtn {
      appearance: none;
      border: 3px solid var(--line);
      border-radius: var(--radius-sm);
      background: #fff;
      color: var(--text);
      font: inherit;
      font-weight: 900;
      padding: 12px 10px;
      box-shadow: 3px 3px 0 var(--line);
      cursor: pointer;
    }
    .toolbtn.accent { background: var(--yellow); }
    .toolbtn.danger { background: #ffd7df; }
    .console {
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 14px;
      min-height: 72vh;
    }
    .hidden { display: none; }
    .hint {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }
    .hint.error {
      color: #bb314a;
      font-weight: 700;
    }
    .footer-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }
    .toggle {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      font-size: 12px;
      color: var(--muted);
      font-weight: 800;
    }
    .toggle input {
      width: 18px;
      height: 18px;
      margin: 0;
      accent-color: var(--purple);
      box-shadow: none;
    }
    #log {
      background: #fffdf8;
      border: 3px solid var(--line);
      border-radius: var(--radius);
      min-height: 430px;
      max-height: 62vh;
      overflow: auto;
      padding: 16px;
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.45;
      font-size: 13px;
      font-family: var(--mono);
      box-shadow: inset 0 0 0 2px rgba(255,255,255,0.42);
    }
    .line { margin: 0 0 8px; }
    .line.stderr { color: #bb314a; }
    .line.meta { color: #6540df; font-weight: 700; }
    .line.chat { color: #63505b; }
    .ansi-bold { font-weight: 700; }
    .ansi-dim { opacity: 0.72; }
    .ansi-italic { font-style: italic; }
    .ansi-underline { text-decoration: underline; }
    form, .stack {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    input, textarea {
      width: 100%;
      border-radius: 18px;
      border: 3px solid var(--line);
      background: #fffdf9;
      color: var(--text);
      font: inherit;
      padding: 13px 14px;
    }
    textarea {
      min-height: 88px;
      resize: vertical;
      font-family: var(--mono);
      box-shadow: 3px 3px 0 var(--line);
    }
    .composer {
      display: grid;
      grid-template-columns: 1fr auto auto;
      gap: 12px;
      align-items: end;
    }
    .composer.prompting textarea {
      background: #fff0fb;
      border-color: var(--purple);
    }
    .composer.editable-prompt textarea {
      background: #f2fff1;
      border-color: #4cb782;
    }
    .sendbtn {
      appearance: none;
      border: 3px solid var(--line);
      border-radius: 20px;
      background: linear-gradient(180deg, #ffe15e 0%, #ffc928 100%);
      color: var(--text);
      font: inherit;
      font-weight: 900;
      min-width: 120px;
      padding: 14px 16px;
      box-shadow: 4px 4px 0 var(--line);
      cursor: pointer;
    }
    .sendbtn:disabled, .toolbtn:disabled {
      opacity: 0.55;
      cursor: default;
    }
    @media (max-width: 820px) {
      .topbar {
        flex-direction: column;
        align-items: flex-start;
      }
      .composer {
        grid-template-columns: 1fr;
      }
      .sendbtn {
        width: 100%;
      }
      #log {
        min-height: 52vh;
        max-height: 52vh;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="card">
      <div class="topbar">
        <div>
          <div class="title">Sonata Remote Term</div>
          <div class="status" id="connectionStatus">Signed out</div>
        </div>
        <div class="status-pill warn" id="controllerStatus">No control</div>
      </div>
      <div class="toolbar hidden" id="actionBar">
        <button class="toolbtn accent" id="takeoverBtn" type="button">Take Over</button>
        <button class="toolbtn" id="logoutBtn" type="button">Sign Out</button>
        <button class="toolbtn danger" id="clearBtn" type="button">Clear</button>
      </div>
      <div class="console">
        <div id="loginCard" class="stack">
          <div class="hint">Authenticate with the shared secret to access the live console.</div>
          <div class="hint hidden" id="authMessage"></div>
          <form id="loginForm">
            <input id="secret" type="password" placeholder="Shared secret" autocomplete="current-password">
            <button class="sendbtn" type="submit">Sign In</button>
          </form>
        </div>
        <div id="consoleCard" class="hidden stack">
          <form id="commandForm" class="composer">
            <textarea id="commandInput" placeholder="Send a term-command..."></textarea>
            <button class="toolbtn hidden" id="exitPromptButton" type="button">Exit</button>
            <button class="sendbtn" id="runButton" type="submit">Send</button>
          </form>
          <div id="log"></div>
          <div class="footer-row">
            <div class="hint">Chat activity is mirrored here too so the terminal feed feels closer to the local experience.</div>
            <label class="toggle">
              <input type="checkbox" id="reverseToggle" checked>
              Newest first
            </label>
          </div>
        </div>
      </div>
    </div>
  </div>
  <script>
    const basePath = __BASE_PATH__;
    const joinPath = (path) => (basePath === '/' || basePath === '' ? path : basePath + path);
    const actionBar = document.getElementById('actionBar');
    const loginCard = document.getElementById('loginCard');
    const consoleCard = document.getElementById('consoleCard');
    const authMessage = document.getElementById('authMessage');
    const loginForm = document.getElementById('loginForm');
    const secretInput = document.getElementById('secret');
    const logEl = document.getElementById('log');
    const commandForm = document.getElementById('commandForm');
    const commandInput = document.getElementById('commandInput');
    const controllerStatus = document.getElementById('controllerStatus');
    const connectionStatus = document.getElementById('connectionStatus');
    const takeoverBtn = document.getElementById('takeoverBtn');
    const logoutBtn = document.getElementById('logoutBtn');
    const clearBtn = document.getElementById('clearBtn');
    const reverseToggle = document.getElementById('reverseToggle');
    const runButton = document.getElementById('runButton');
    const exitPromptButton = document.getElementById('exitPromptButton');
    let eventSource = null;
    let reconnectTimer = null;
    const blankState = () => ({ authenticated: false, session_id: null, is_controller: false, controller_id: null, busy: false, pending_prompt: null, history: [] });
    let state = blankState();

    function setAuthMessage(text, tone='info') {
      authMessage.textContent = text || '';
      authMessage.classList.toggle('hidden', !text);
      authMessage.classList.toggle('error', tone === 'error');
    }

    function resetClientState(message='') {
      if (eventSource) eventSource.close();
      if (reconnectTimer) clearTimeout(reconnectTimer);
      eventSource = null;
      reconnectTimer = null;
      state = blankState();
      logEl.innerHTML = '';
      commandInput.value = '';
      setAuthMessage(message, message ? 'error' : 'info');
      syncUi();
    }

    function setMessage(text, tone='info') {
      if (!text) return;
      if (!state.authenticated) {
        setAuthMessage(text, tone);
        return;
      }
      appendLine(`[status] ${text}`, 'meta');
    }

    function clearPromptState(message='Prompt exited.') {
      state.pending_prompt = null;
      delete commandInput.dataset.promptId;
      syncUi();
      if (message) setMessage(message);
    }

    function escapeHtml(value) {
      return value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
    }

    function styleToCss(style) {
      const css = [];
      if (style.color) css.push(`color:${style.color}`);
      if (style.background) css.push(`background-color:${style.background}`);
      return css.join(';');
    }

    function styleToClass(style) {
      return [
        style.bold ? 'ansi-bold' : '',
        style.dim ? 'ansi-dim' : '',
        style.italic ? 'ansi-italic' : '',
        style.underline ? 'ansi-underline' : '',
      ].filter(Boolean).join(' ');
    }

    function cloneStyle(style) {
      return { ...style };
    }

    function resetStyle() {
      return { bold: false, dim: false, italic: false, underline: false, color: null, background: null };
    }

    function ansiColor(code) {
      const colors = {
        30: '#1f2a33', 31: '#ff7b72', 32: '#7ee787', 33: '#f2cc60',
        34: '#79c0ff', 35: '#d2a8ff', 36: '#76e3ea', 37: '#e6edf3',
        90: '#6e7681', 91: '#ffa198', 92: '#56d364', 93: '#e3b341',
        94: '#58a6ff', 95: '#bc8cff', 96: '#39c5cf', 97: '#f0f6fc',
      };
      return colors[code] || null;
    }

    function ansiBgColor(code) {
      const colors = {
        40: '#1f2a33', 41: '#7f1d1d', 42: '#173b2a', 43: '#5b450e',
        44: '#17365d', 45: '#512a79', 46: '#114850', 47: '#9aa4ad',
        100: '#4b5563', 101: '#991b1b', 102: '#14532d', 103: '#713f12',
        104: '#1d4ed8', 105: '#6b21a8', 106: '#155e75', 107: '#d1d5db',
      };
      return colors[code] || null;
    }

    function ansi256Color(code) {
      if (code < 0 || code > 255) return null;
      const system = {
        0: '#000000', 1: '#800000', 2: '#008000', 3: '#808000',
        4: '#000080', 5: '#800080', 6: '#008080', 7: '#c0c0c0',
        8: '#808080', 9: '#ff0000', 10: '#00ff00', 11: '#ffff00',
        12: '#0000ff', 13: '#ff00ff', 14: '#00ffff', 15: '#ffffff',
      };
      if (code in system) return system[code];
      if (code >= 232) {
        const channel = 8 + (code - 232) * 10;
        return `rgb(${channel}, ${channel}, ${channel})`;
      }
      const index = code - 16;
      const steps = [0, 95, 135, 175, 215, 255];
      const r = steps[Math.floor(index / 36) % 6];
      const g = steps[Math.floor(index / 6) % 6];
      const b = steps[index % 6];
      return `rgb(${r}, ${g}, ${b})`;
    }

    function applyAnsiCode(style, code) {
      if (code === 0) return resetStyle();
      const next = cloneStyle(style);
      if (code === 1) next.bold = true;
      else if (code === 2) next.dim = true;
      else if (code === 3) next.italic = true;
      else if (code === 4) next.underline = true;
      else if (code === 22) { next.bold = false; next.dim = false; }
      else if (code === 23) next.italic = false;
      else if (code === 24) next.underline = false;
      else if (code === 39) next.color = null;
      else if (code === 49) next.background = null;
      else if (ansiColor(code)) next.color = ansiColor(code);
      else if (ansiBgColor(code)) next.background = ansiBgColor(code);
      return next;
    }

    function applyAnsiCodes(style, codes) {
      let next = cloneStyle(style);
      for (let index = 0; index < codes.length; index += 1) {
        const code = codes[index];
        if ((code === 38 || code === 48) && index + 1 < codes.length) {
          const target = code === 38 ? 'color' : 'background';
          const mode = codes[index + 1];
          if (mode === 2 && index + 4 < codes.length) {
            const r = codes[index + 2];
            const g = codes[index + 3];
            const b = codes[index + 4];
            next[target] = `rgb(${r}, ${g}, ${b})`;
            index += 4;
            continue;
          }
          if (mode === 5 && index + 2 < codes.length) {
            next[target] = ansi256Color(codes[index + 2]);
            index += 2;
            continue;
          }
        }
        next = applyAnsiCode(next, code);
      }
      return next;
    }

    function ansiToHtml(text) {
      const pattern = /\x1b\\[([0-9;]*)m/g;
      let style = resetStyle();
      let rendered = '';
      let lastIndex = 0;
      let match;
      while ((match = pattern.exec(text)) !== null) {
        const chunk = text.slice(lastIndex, match.index);
        if (chunk) {
          const css = styleToCss(style);
          const classes = styleToClass(style);
          rendered += `<span${classes ? ` class="${classes}"` : ''}${css ? ` style="${css}"` : ''}>${escapeHtml(chunk)}</span>`;
        }
        const codes = (match[1] || '0').split(';').filter(Boolean).map(Number);
        style = applyAnsiCodes(style, codes.length ? codes : [0]);
        lastIndex = pattern.lastIndex;
      }
      const tail = text.slice(lastIndex);
      if (tail) {
        const css = styleToCss(style);
        const classes = styleToClass(style);
        rendered += `<span${classes ? ` class="${classes}"` : ''}${css ? ` style="${css}"` : ''}>${escapeHtml(tail)}</span>`;
      }
      return rendered || escapeHtml(text);
    }

    function appendLine(text, kind='stdout') {
      const line = document.createElement('div');
      line.className = 'line ' + (kind === 'stderr' ? 'stderr' : kind === 'meta' ? 'meta' : kind === 'chat' ? 'chat' : '');
      line.innerHTML = ansiToHtml(text);
      if (reverseToggle.checked) {
        logEl.prepend(line);
        logEl.scrollTop = 0;
      } else {
        logEl.appendChild(line);
        logEl.scrollTop = logEl.scrollHeight;
      }
    }

    function resetLog(history) {
      logEl.innerHTML = '';
      history.forEach((event) => handleEvent(event, true));
    }

    function syncUi() {
      const signedIn = !!state.authenticated;
      const isEditablePrompt = !!(state.pending_prompt && state.pending_prompt.editable);
      loginCard.classList.toggle('hidden', signedIn);
      consoleCard.classList.toggle('hidden', !signedIn);
      actionBar.classList.toggle('hidden', !signedIn);
      controllerStatus.classList.toggle('hidden', !signedIn);
      connectionStatus.textContent = signedIn
        ? (eventSource ? 'Connected' : 'Reconnecting...')
        : 'Signed out';
      controllerStatus.textContent = state.is_controller ? 'You own control' : (state.controller_id ? 'Another session owns control' : 'No control');
      controllerStatus.className = 'status-pill ' + (state.is_controller ? 'ok' : 'warn');
      controllerStatus.classList.toggle('hidden', !signedIn);
      const blocked = !signedIn || !state.is_controller || (state.busy && !state.pending_prompt);
      runButton.disabled = blocked;
      commandInput.disabled = blocked;
      exitPromptButton.disabled = !signedIn || !state.is_controller || !state.pending_prompt;
      exitPromptButton.classList.toggle('hidden', !state.pending_prompt);
      takeoverBtn.disabled = !signedIn;
      if (signedIn) setAuthMessage('');
      if (state.pending_prompt) {
        commandForm.classList.add('prompting');
        commandForm.classList.toggle('editable-prompt', isEditablePrompt);
        commandInput.placeholder = state.pending_prompt.text || 'Enter follow-up input...';
        runButton.textContent = 'Reply';
        if (commandInput.dataset.promptId !== state.pending_prompt.prompt_id) {
          commandInput.dataset.promptId = state.pending_prompt.prompt_id;
          commandInput.value = state.pending_prompt.current ?? '';
        }
      } else {
        commandForm.classList.remove('prompting');
        commandForm.classList.remove('editable-prompt');
        commandInput.placeholder = 'Send a term-command...';
        runButton.textContent = 'Send';
        delete commandInput.dataset.promptId;
      }
    }

    async function api(path, options={}) {
      const response = await fetch(joinPath(path), {
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        ...options,
      });
      let data = {};
      try { data = await response.json(); } catch (_err) {}
      if (!response.ok) {
        const error = new Error(data.message || 'Request failed');
        error.data = data;
        throw error;
      }
      return data;
    }

    async function ensureControl() {
      return api('/api/control', {
        method: 'POST',
        body: JSON.stringify({ action: 'takeover' }),
      });
    }

    function connectEvents() {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (eventSource) eventSource.close();
      eventSource = new EventSource(joinPath('/api/events'), { withCredentials: true });
      eventSource.onmessage = (event) => handleEvent(JSON.parse(event.data), false);
      eventSource.onerror = () => {
        if (eventSource) eventSource.close();
        eventSource = null;
        syncUi();
        if (state.authenticated && !reconnectTimer) {
          reconnectTimer = setTimeout(async () => {
            reconnectTimer = null;
            try {
              const data = await api('/api/session', { method: 'GET' });
              state = { ...state, ...data, authenticated: true };
              resetLog(state.history || []);
              connectEvents();
              syncUi();
              setMessage('Reconnected.');
            } catch (_err) {
              syncUi();
              connectEvents();
            }
          }, 1000);
        }
      };
    }

    function handleEvent(event, fromHistory) {
      if (event.type === 'snapshot') {
        state = { ...state, ...event, authenticated: true };
        if (fromHistory) return;
        resetLog(event.history || []);
        syncUi();
        return;
      }
      if (event.type === 'output') appendLine(event.text, event.stream);
      if (event.type === 'command') {
        appendLine((event.phase === 'start' ? '>> ' : '<< ') + event.command, 'meta');
        state.busy = event.phase === 'start';
      }
      if (event.type === 'controller') {
        state.controller_id = event.controller_id;
        state.is_controller = !!state.session_id && state.controller_id === state.session_id;
      }
      if (event.type === 'prompt') {
        state.pending_prompt = event.prompt;
        appendLine(`[prompt] ${event.prompt.text || 'Follow-up input required.'}`, 'meta');
        commandInput.dataset.promptId = event.prompt.prompt_id;
        commandInput.value = event.prompt.current ?? '';
        setTimeout(() => {
          commandInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
          commandInput.focus();
          if (event.prompt.editable) {
            commandInput.setSelectionRange(0, commandInput.value.length);
          } else {
            commandInput.setSelectionRange(commandInput.value.length, commandInput.value.length);
          }
        }, 0);
      }
      if (event.type === 'prompt_resolved') {
        state.pending_prompt = null;
        setMessage('Prompt input accepted.');
      }
      syncUi();
    }

    async function loadSession() {
      try {
        let data = await api('/api/session', { method: 'GET' });
        state = { ...state, ...data, authenticated: true };
        if (!state.is_controller) {
          try {
            await ensureControl();
            data = await api('/api/session', { method: 'GET' });
            state = { ...state, ...data, authenticated: true };
          } catch (err) {
            setMessage(err.message, 'error');
          }
        }
        resetLog(state.history || []);
        connectEvents();
        syncUi();
        setMessage(state.is_controller ? 'Connected and in control.' : 'Connected, but another session currently owns control.');
      } catch (err) {
        resetClientState(err.message === 'Authentication required.' ? '' : err.message);
        throw err;
      }
    }

    loginForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      setAuthMessage('');
      try {
        await api('/api/login', {
          method: 'POST',
          body: JSON.stringify({ secret: secretInput.value }),
        });
        secretInput.value = '';
        await loadSession();
      } catch (err) {
        setMessage(err.message, 'error');
      }
    });

    commandForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const rawValue = commandInput.value;
      const submittedPromptId = state.pending_prompt ? state.pending_prompt.prompt_id : null;
      if (!rawValue.trim()) return;
      try {
        await ensureControl();
        const result = state.pending_prompt
          ? await api('/api/prompt', {
              method: 'POST',
              body: JSON.stringify({ prompt_id: state.pending_prompt.prompt_id, value: rawValue }),
            })
          : await api('/api/command', {
              method: 'POST',
              body: JSON.stringify({ command: rawValue }),
            });
        const pendingPromptChanged = state.pending_prompt && state.pending_prompt.prompt_id !== submittedPromptId;
        if (!pendingPromptChanged) {
          commandInput.value = '';
        }
        setMessage(result.message || (state.pending_prompt ? 'Prompt submitted.' : 'Command sent.'));
      } catch (err) {
        if (state.pending_prompt && err.data && err.data.prompt_active === false) {
          clearPromptState('Prompt expired. Your text is still here; send it again if you still want to run it.');
          return;
        }
        setMessage(err.message, 'error');
      }
    });

    commandInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        commandForm.requestSubmit();
      }
    });

    exitPromptButton.addEventListener('click', async () => {
      if (!state.pending_prompt) return;
      try {
        await ensureControl();
        const result = await api('/api/prompt/exit', {
          method: 'POST',
          body: JSON.stringify({ prompt_id: state.pending_prompt.prompt_id }),
        });
        clearPromptState(result.message || 'Prompt exited.');
      } catch (err) {
        if (err.data && err.data.prompt_active === false) {
          clearPromptState('Prompt already expired.');
          return;
        }
        setMessage(err.message, 'error');
      }
    });

    takeoverBtn.addEventListener('click', async () => {
      try {
        const result = await ensureControl();
        setMessage(result.message);
        await loadSession();
      } catch (err) {
        setMessage(err.message, 'error');
      }
    });

    logoutBtn.addEventListener('click', async () => {
      try { await api('/api/logout', { method: 'POST', body: JSON.stringify({}) }); } catch (_err) {}
      resetClientState();
    });

    clearBtn.addEventListener('click', async () => {
      try {
        await api('/api/debug/clear-sessions', { method: 'POST', body: JSON.stringify({}) });
        resetClientState();
      } catch (err) {
        setMessage(err.message, 'error');
      }
    });

    reverseToggle.addEventListener('change', () => {
      resetLog(state.history || []);
    });

    resetClientState();
    loadSession().catch(() => {});
  </script>
</body>
</html>""".replace("__BASE_PATH__", json.dumps(safe_base))
