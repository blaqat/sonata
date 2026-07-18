"""Async Cursor Cloud Agents v1 HTTP client with SSE streaming."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Any
import httpx

from .config import CursorCloudConfig
from .errors import (
    AgentRunError,
    AuthenticationError,
    BusyRunError,
    CursorCloudError,
    RateLimitError,
    StreamExpiredError,
    TransportError,
    ValidationError,
)
from .models import AgentRecord, ModelInfo, RunRecord, StreamEvent

logger = logging.getLogger("sonata.cursor.client")


def parse_sse_chunk(buffer: str) -> tuple[list[StreamEvent], str]:
    """Parse complete SSE events from a text buffer; return events + remainder."""
    events: list[StreamEvent] = []
    parts = buffer.split("\n\n")
    remainder = parts.pop() if parts else ""
    # If buffer ended with \n\n, last part is empty remainder.
    if buffer.endswith("\n\n"):
        if remainder:
            parts.append(remainder)
            remainder = ""
    for block in parts:
        block = block.strip("\n")
        if not block or block.startswith(":"):
            continue
        event_name = "message"
        event_id: str | None = None
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith(":"):
                continue
            if line.startswith("id:"):
                event_id = line[3:].lstrip()
            elif line.startswith("event:"):
                event_name = line[6:].lstrip() or "message"
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
            elif line.startswith("data"):
                # `data` with no colon => empty data per SSE spec edge cases
                data_lines.append("")
        raw = "\n".join(data_lines)
        payload: dict[str, Any]
        if not raw:
            payload = {}
        else:
            try:
                parsed = json.loads(raw)
                payload = parsed if isinstance(parsed, dict) else {"value": parsed}
            except json.JSONDecodeError:
                payload = {"text": raw}
        events.append(StreamEvent(event=event_name, data=payload, id=event_id))
    return events, remainder


class CursorCloudClient:
    """Reusable async client for Cursor Cloud Agents API v1."""

    def __init__(self, config: CursorCloudConfig, *, client: httpx.AsyncClient | None = None):
        self.config = config
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> "CursorCloudClient":
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(
                connect=self.config.connect_timeout_seconds,
                read=self.config.read_timeout_seconds,
                write=self.config.connect_timeout_seconds,
                pool=self.config.connect_timeout_seconds,
            )
            self._client = httpx.AsyncClient(
                base_url=self.config.api_base_url,
                timeout=timeout,
                auth=httpx.BasicAuth(self.config.api_key, ""),
                headers={"Accept": "application/json"},
            )
        return self._client

    def _stream_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.config.connect_timeout_seconds,
            read=self.config.stream_timeout_seconds,
            write=self.config.connect_timeout_seconds,
            pool=self.config.connect_timeout_seconds,
        )

    def _map_error(self, response: httpx.Response) -> CursorCloudError:
        try:
            body = response.json()
        except Exception:
            body = {"message": response.text}
        code = ""
        message = ""
        if isinstance(body, dict):
            err = body.get("error") if isinstance(body.get("error"), dict) else body
            code = str(err.get("code") or body.get("code") or "")
            message = str(
                err.get("message") or body.get("message") or body.get("error") or ""
            )
        message = message or f"HTTP {response.status_code}"
        retry_after = None
        if "Retry-After" in response.headers:
            try:
                retry_after = float(response.headers["Retry-After"])
            except ValueError:
                retry_after = None

        if response.status_code in (401, 403):
            return AuthenticationError(message, code=code or "auth_error")
        if response.status_code == 409 and (
            "busy" in code or "busy" in message.lower() or code == "agent_busy"
        ):
            return BusyRunError(message, code=code or "agent_busy")
        if response.status_code == 409:
            return AgentRunError(message, code=code or "conflict")
        if response.status_code == 410 or code == "stream_expired":
            return StreamExpiredError(message, code=code or "stream_expired")
        if response.status_code == 429:
            return RateLimitError(
                message, retry_after=retry_after, code=code or "rate_limit"
            )
        if response.status_code == 400:
            return ValidationError(message, code=code or "validation_error")
        if response.status_code >= 500:
            return TransportError(message, code=code or "server_error")
        return AgentRunError(message, code=code or f"http_{response.status_code}")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        idempotent: bool = False,
        accept: str | None = None,
        extra_headers: dict[str, str] | None = None,
        stream: bool = False,
        timeout: httpx.Timeout | None = None,
    ) -> httpx.Response:
        client = await self._ensure_client()
        headers: dict[str, str] = {}
        if accept:
            headers["Accept"] = accept
        if extra_headers:
            headers.update(extra_headers)
        req_timeout = timeout

        attempts = 3 if idempotent else 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                if stream:
                    request = client.build_request(
                        method,
                        path,
                        json=json_body,
                        params=params,
                        headers=headers,
                        timeout=req_timeout or self._stream_timeout(),
                    )
                    response = await client.send(request, stream=True)
                else:
                    response = await client.request(
                        method,
                        path,
                        json=json_body,
                        params=params,
                        headers=headers,
                        timeout=req_timeout,
                    )
            except httpx.TimeoutException as exc:
                last_error = TransportError(str(exc))
                if not idempotent or attempt + 1 >= attempts:
                    raise last_error from exc
                await asyncio.sleep(min(2**attempt, 8))
                continue
            except httpx.HTTPError as exc:
                last_error = TransportError(str(exc))
                if not idempotent or attempt + 1 >= attempts:
                    raise last_error from exc
                await asyncio.sleep(min(2**attempt, 8))
                continue

            if response.status_code in (429, 500, 502, 503, 504) and idempotent:
                err = self._map_error(response)
                if stream:
                    await response.aclose()
                last_error = err
                if attempt + 1 >= attempts:
                    raise err
                delay = getattr(err, "retry_after", None) or min(2**attempt, 8)
                await asyncio.sleep(float(delay))
                continue

            if response.status_code >= 400:
                if stream:
                    # Consume body for error mapping then close.
                    await response.aread()
                    err = self._map_error(response)
                    await response.aclose()
                    raise err
                raise self._map_error(response)
            return response

        raise last_error or TransportError("Request failed")

    async def create_agent(
        self,
        prompt_text: str,
        *,
        images: list[dict[str, Any]] | None = None,
        model: str | None = None,
        repository_url: str | None = None,
        starting_ref: str | None = None,
        auto_create_pr: bool | None = None,
        name: str | None = None,
    ) -> tuple[AgentRecord, RunRecord]:
        prompt: dict[str, Any] = {"text": prompt_text}
        if images:
            prompt["images"] = images
        body: dict[str, Any] = {"prompt": prompt}
        if model:
            body["model"] = {"id": model}
        repo_url = repository_url or self.config.default_repository_url
        ref = starting_ref or self.config.default_ref
        if repo_url:
            body["repos"] = [{"url": repo_url, "startingRef": ref}]
        pr_flag = (
            self.config.auto_create_pr if auto_create_pr is None else auto_create_pr
        )
        body["autoCreatePR"] = bool(pr_flag)
        if name:
            body["name"] = name[:100]

        response = await self._request("POST", "/v1/agents", json_body=body)
        data = response.json()
        agent = AgentRecord.from_api(data.get("agent") or data)
        run_data = data.get("run") or {}
        if not isinstance(run_data, dict):
            run_data = {}
        if not (run_data.get("id") or run_data.get("runId")) and agent.latest_run_id:
            run_data = {
                "id": agent.latest_run_id,
                "agentId": agent.id,
                "status": run_data.get("status") or "CREATING",
            }
        # Some create responses omit `run` entirely; resolve via GET agent.
        if not (run_data.get("id") or run_data.get("runId")) and agent.id:
            try:
                refreshed = await self.get_agent(agent.id)
                if refreshed.latest_run_id:
                    agent = refreshed
                    run_data = {
                        "id": refreshed.latest_run_id,
                        "agentId": agent.id,
                        "status": "CREATING",
                    }
            except CursorCloudError:
                pass
        run = RunRecord.from_api(run_data)
        if not run.id:
            raise ValidationError(
                "create_agent response missing run id",
                user_message=(
                    "Cursor created an agent but no run id was returned. "
                    "Try again in a moment."
                ),
                code="missing_run_id",
            )
        if not run.agent_id:
            run.agent_id = agent.id
        return agent, run

    async def create_run(
        self,
        agent_id: str,
        prompt_text: str,
        *,
        images: list[dict[str, Any]] | None = None,
    ) -> RunRecord:
        """Follow-up run. Official API has no model field on this endpoint."""
        prompt: dict[str, Any] = {"text": prompt_text}
        if images:
            prompt["images"] = images
        body = {"prompt": prompt}
        response = await self._request(
            "POST", f"/v1/agents/{agent_id}/runs", json_body=body
        )
        data = response.json()
        run_data = data.get("run") if isinstance(data.get("run"), dict) else data
        if not isinstance(run_data, dict):
            run_data = {}
        run = RunRecord.from_api(run_data)
        if not run.id:
            raise ValidationError(
                "create_run response missing run id",
                user_message=(
                    "Cursor accepted the follow-up but no run id was returned. "
                    "Try again in a moment."
                ),
                code="missing_run_id",
            )
        if not run.agent_id:
            run.agent_id = agent_id
        return run

    async def get_agent(self, agent_id: str) -> AgentRecord:
        response = await self._request(
            "GET", f"/v1/agents/{agent_id}", idempotent=True
        )
        return AgentRecord.from_api(response.json())

    async def list_agents(
        self, *, limit: int = 20, cursor: str | None = None
    ) -> tuple[list[AgentRecord], str | None]:
        params: dict[str, Any] = {"limit": min(max(limit, 1), 100)}
        if cursor:
            params["cursor"] = cursor
        response = await self._request(
            "GET", "/v1/agents", params=params, idempotent=True
        )
        data = response.json()
        items = [AgentRecord.from_api(i) for i in data.get("items") or []]
        return items, data.get("nextCursor")

    @staticmethod
    def _is_run_not_found(exc: Exception) -> bool:
        text = " ".join(
            str(part)
            for part in (
                exc,
                getattr(exc, "user_message", ""),
                getattr(exc, "code", ""),
            )
            if part
        ).lower()
        return "not found" in text or "404" in text

    async def get_run(
        self,
        agent_id: str,
        run_id: str,
        *,
        retries: int = 4,
        retry_delay_s: float = 0.6,
    ) -> RunRecord:
        """GET run, retrying briefly on not-found (create can race read)."""
        if not run_id:
            raise ValidationError(
                "missing run id",
                user_message="No Cursor run id to fetch.",
                code="missing_run_id",
            )
        last_exc: Exception | None = None
        attempts = max(1, int(retries) + 1)
        for attempt in range(attempts):
            try:
                response = await self._request(
                    "GET",
                    f"/v1/agents/{agent_id}/runs/{run_id}",
                    idempotent=True,
                )
                run = RunRecord.from_api(response.json())
                if not run.id:
                    run.id = run_id
                if not run.agent_id:
                    run.agent_id = agent_id
                return run
            except CursorCloudError as exc:
                last_exc = exc
                if attempt + 1 >= attempts or not self._is_run_not_found(exc):
                    raise
                await asyncio.sleep(retry_delay_s * (attempt + 1))
        assert last_exc is not None
        raise last_exc

    async def cancel_run(self, agent_id: str, run_id: str) -> str:
        response = await self._request(
            "POST",
            f"/v1/agents/{agent_id}/runs/{run_id}/cancel",
        )
        data = response.json()
        return str(data.get("id") or run_id)

    async def list_models(self) -> list[ModelInfo]:
        response = await self._request("GET", "/v1/models", idempotent=True)
        data = response.json()
        return [ModelInfo.from_api(i) for i in data.get("items") or []]

    @staticmethod
    def _looks_like_stream_unavailable(exc: BaseException) -> bool:
        code = str(getattr(exc, "code", "") or "").lower()
        message = " ".join(
            str(part)
            for part in (exc, getattr(exc, "user_message", ""), getattr(exc, "message", ""))
            if part
        ).lower()
        if code in {"stream_expired", "stream_unavailable", "gone"}:
            return True
        needles = (
            "no longer available",
            "stream expired",
            "stream is no longer",
            "stream unavailable",
            "run stream is no longer",
        )
        return any(n in message for n in needles)

    async def stream_run(
        self,
        agent_id: str,
        run_id: str,
        *,
        last_event_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        headers: dict[str, str] = {}
        if last_event_id:
            headers["Last-Event-ID"] = last_event_id

        logger.warning(
            "cursor.stream_open agent=%s run=%s last_event_id=%s",
            agent_id,
            run_id,
            last_event_id,
        )
        try:
            response = await self._request(
                "GET",
                f"/v1/agents/{agent_id}/runs/{run_id}/stream",
                accept="text/event-stream",
                extra_headers=headers,
                stream=True,
                idempotent=False,
                timeout=self._stream_timeout(),
            )
        except StreamExpiredError:
            logger.warning(
                "cursor.stream_open_410 agent=%s run=%s last_event_id=%s",
                agent_id,
                run_id,
                last_event_id,
            )
            raise
        except CursorCloudError as exc:
            logger.warning(
                "cursor.stream_open_failed agent=%s run=%s http=%s code=%s msg=%r",
                agent_id,
                run_id,
                getattr(exc, "status", None),
                getattr(exc, "code", None),
                (getattr(exc, "user_message", None) or str(exc))[:300],
            )
            raise

        # Consume via explicit anext/aclose so early consumer break (after
        # terminal `done`) does not leave httpcore's byte-stream aiter to
        # log "async generator ignored GeneratorExit".
        buffer = ""
        byte_iter = response.aiter_text()
        event_count = 0
        try:
            while True:
                try:
                    chunk = await byte_iter.__anext__()
                except StopAsyncIteration:
                    break
                buffer += chunk
                events, buffer = parse_sse_chunk(buffer)
                for event in events:
                    event_count += 1
                    if event.event in {"error", "result", "done"}:
                        logger.warning(
                            "cursor.sse_event agent=%s run=%s event=%s data=%r",
                            agent_id,
                            run_id,
                            event.event,
                            event.data,
                        )
                    yield event
            if buffer.strip():
                events, _ = parse_sse_chunk(buffer + "\n\n")
                for event in events:
                    event_count += 1
                    if event.event in {"error", "result", "done"}:
                        logger.warning(
                            "cursor.sse_event agent=%s run=%s event=%s data=%r",
                            agent_id,
                            run_id,
                            event.event,
                            event.data,
                        )
                    yield event
            logger.warning(
                "cursor.stream_closed agent=%s run=%s events=%s",
                agent_id,
                run_id,
                event_count,
            )
        except StreamExpiredError:
            logger.warning(
                "cursor.stream_mid_410 agent=%s run=%s events=%s",
                agent_id,
                run_id,
                event_count,
            )
            raise
        except httpx.HTTPError as exc:
            logger.warning(
                "cursor.stream_transport agent=%s run=%s events=%s err=%r",
                agent_id,
                run_id,
                event_count,
                str(exc)[:300],
            )
            raise TransportError(str(exc)) from exc
        finally:
            with contextlib.suppress(Exception):
                await byte_iter.aclose()
            with contextlib.suppress(Exception):
                if not response.is_closed:
                    await response.aclose()

    async def stream_run_with_fallback(
        self,
        agent_id: str,
        run_id: str,
        *,
        last_event_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream events; on stream-gone fall back to GET run / pollable error."""
        try:
            async for event in self.stream_run(
                agent_id, run_id, last_event_id=last_event_id
            ):
                yield event
            return
        except StreamExpiredError as exc:
            logger.warning(
                "cursor.stream_fallback_get agent=%s run=%s reason=410 msg=%r",
                agent_id,
                run_id,
                (exc.user_message or str(exc))[:300],
            )
            run = await self.get_run(agent_id, run_id)
            logger.warning(
                "cursor.stream_fallback_status agent=%s run=%s status=%s has_result=%s",
                agent_id,
                run_id,
                run.status.value,
                bool(run.result),
            )
            # If the run is still active, surface a stream-unavailable error so
            # RunTracker polls instead of treating a synthetic result as done.
            if not run.status.is_terminal:
                yield StreamEvent(
                    event="error",
                    data={
                        "code": "stream_unavailable",
                        "message": "Run stream is no longer available",
                    },
                )
                return
            payload: dict[str, Any] = {
                "runId": run.id,
                "status": run.status.value,
            }
            if run.result:
                payload["text"] = run.result
            if run.duration_ms is not None:
                payload["durationMs"] = run.duration_ms
            if run.git:
                payload["git"] = run.git
            yield StreamEvent(event="result", data=payload)
            yield StreamEvent(event="done", data={})
        except ValidationError as exc:
            # Must run before CursorCloudError (ValidationError subclasses it).
            if last_event_id and (
                "last_event" in str(exc).lower() or "invalid_last_event" in (exc.code or "")
            ):
                logger.warning(
                    "cursor.stream_retry_without_last_event agent=%s run=%s",
                    agent_id,
                    run_id,
                )
                async for event in self.stream_run(agent_id, run_id, last_event_id=None):
                    yield event
                return
            raise
        except CursorCloudError as exc:
            if self._looks_like_stream_unavailable(exc):
                logger.warning(
                    "cursor.stream_open_as_unavailable agent=%s run=%s "
                    "http=%s code=%s msg=%r — yielding stream_unavailable",
                    agent_id,
                    run_id,
                    getattr(exc, "status", None),
                    getattr(exc, "code", None),
                    (exc.user_message or str(exc))[:300],
                )
                yield StreamEvent(
                    event="error",
                    data={
                        "code": "stream_unavailable",
                        "message": exc.user_message
                        or "Run stream is no longer available",
                    },
                )
                return
            raise
