"""Normalized Cursor Cloud / Discord-facing errors with safe user messages."""

from __future__ import annotations


class CursorCloudError(Exception):
    """Base error. ``user_message`` is safe to show in Discord."""

    def __init__(self, message: str, *, user_message: str | None = None, code: str | None = None):
        super().__init__(message)
        self.code = code
        self.user_message = user_message or message


class AuthenticationError(CursorCloudError):
    def __init__(self, message: str = "Cursor API authentication failed", **kwargs):
        super().__init__(
            message,
            user_message=kwargs.pop(
                "user_message",
                "Cursor API authentication failed. Check `CURSOR_API_KEY`.",
            ),
            code=kwargs.pop("code", "auth_error"),
            **kwargs,
        )


class AuthorizationError(CursorCloudError):
    def __init__(self, message: str = "Not authorized for Cursor commands", **kwargs):
        super().__init__(
            message,
            user_message=kwargs.pop("user_message", "You are not allowed to use Cursor commands."),
            code=kwargs.pop("code", "forbidden"),
            **kwargs,
        )


class ValidationError(CursorCloudError):
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            user_message=kwargs.pop("user_message", message),
            code=kwargs.pop("code", "validation_error"),
            **kwargs,
        )


class RateLimitError(CursorCloudError):
    def __init__(
        self,
        message: str = "Cursor API rate limited",
        *,
        retry_after: float | None = None,
        **kwargs,
    ):
        super().__init__(
            message,
            user_message=kwargs.pop(
                "user_message",
                "Cursor API rate limit hit. Try again shortly.",
            ),
            code=kwargs.pop("code", "rate_limit"),
            **kwargs,
        )
        self.retry_after = retry_after


class BusyRunError(CursorCloudError):
    def __init__(self, message: str = "Agent already has an active run", **kwargs):
        super().__init__(
            message,
            user_message=kwargs.pop(
                "user_message",
                "This agent is busy. Use `/cursor stop` then retry.",
            ),
            code=kwargs.pop("code", "agent_busy"),
            **kwargs,
        )


class StreamExpiredError(CursorCloudError):
    def __init__(self, message: str = "SSE stream expired", **kwargs):
        super().__init__(
            message,
            user_message=kwargs.pop(
                "user_message",
                "Live stream expired; fetching latest run state.",
            ),
            code=kwargs.pop("code", "stream_expired"),
            **kwargs,
        )


class TransportError(CursorCloudError):
    def __init__(self, message: str = "Cursor API transport error", **kwargs):
        super().__init__(
            message,
            user_message=kwargs.pop(
                "user_message",
                "Could not reach the Cursor API. Try again later.",
            ),
            code=kwargs.pop("code", "transport_error"),
            **kwargs,
        )


class AgentRunError(CursorCloudError):
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            user_message=kwargs.pop("user_message", message),
            code=kwargs.pop("code", "agent_run_error"),
            **kwargs,
        )


class ConfigurationError(CursorCloudError):
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            user_message=kwargs.pop("user_message", message),
            code=kwargs.pop("code", "config_error"),
            **kwargs,
        )


class OwnershipError(CursorCloudError):
    def __init__(self, message: str = "Session not owned by caller", **kwargs):
        super().__init__(
            message,
            user_message=kwargs.pop(
                "user_message",
                "That session is not available in this channel.",
            ),
            code=kwargs.pop("code", "ownership_error"),
            **kwargs,
        )


class StaleStateError(CursorCloudError):
    def __init__(self, message: str = "Request state is stale", **kwargs):
        super().__init__(
            message,
            user_message=kwargs.pop(
                "user_message",
                "This control is no longer valid.",
            ),
            code=kwargs.pop("code", "stale_state"),
            **kwargs,
        )


class ApprovalRequiredError(CursorCloudError):
    def __init__(self, message: str = "Approval required", *, request_id: str | None = None, **kwargs):
        super().__init__(
            message,
            user_message=kwargs.pop(
                "user_message",
                "Approval required before this Cursor run can start.",
            ),
            code=kwargs.pop("code", "approval_required"),
            **kwargs,
        )
        self.request_id = request_id


class GrantConsumedError(CursorCloudError):
    """API submission failed after a one-run grant was consumed — fail closed."""

    def __init__(self, message: str = "Grant consumed but API submit failed", **kwargs):
        super().__init__(
            message,
            user_message=kwargs.pop(
                "user_message",
                "Approval was consumed but the run could not be submitted. "
                "Request a new approval — the previous one cannot be reused.",
            ),
            code=kwargs.pop("code", "grant_consumed_submit_failed"),
            **kwargs,
        )
