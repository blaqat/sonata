"""Tier authorization, approvals, grants, audit, and image retention."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import timedelta
from typing import Any, Protocol

from .config import AccessConfig, CursorCloudConfig
from .errors import (
    AuthorizationError,
    GrantConsumedError,
    StaleStateError,
    ValidationError,
)
from .models import (
    AccessAuditEvent,
    AccessTier,
    ApprovalDecision,
    ApprovalRequest,
    ImageInput,
    ImageRetention,
    RunGrant,
    RunRequestEnvelope,
    ScopeKey,
    dt_from_iso,
    utcnow,
)


def envelope_hash(envelope: RunRequestEnvelope) -> str:
    payload = json.dumps(envelope.canonical_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class AccessStore(Protocol):
    async def get_overlay(self) -> dict[str, Any]: ...

    async def set_overlay(self, overlay: dict[str, Any]) -> None: ...

    async def list_requests(self) -> list[ApprovalRequest]: ...

    async def get_request(self, request_id: str) -> ApprovalRequest | None: ...

    async def save_request(self, request: ApprovalRequest) -> ApprovalRequest: ...

    async def list_grants(self) -> list[RunGrant]: ...

    async def get_grant(self, grant_id: str) -> RunGrant | None: ...

    async def save_grant(self, grant: RunGrant) -> RunGrant: ...

    async def append_audit(self, event: AccessAuditEvent) -> None: ...

    async def list_audit(self, *, limit: int = 50) -> list[AccessAuditEvent]: ...

    def lock_for(self, key: str) -> asyncio.Lock: ...


class MemoryAccessStore:
    def __init__(self, *, audit_limit: int = 200):
        self.audit_limit = audit_limit
        self._overlay: dict[str, Any] = {
            "tier1_user_ids": {},
            "tier2_user_ids": {},
            # values: "1" | "2" | "reset" (reset means file-config default)
        }
        self._requests: dict[str, ApprovalRequest] = {}
        self._grants: dict[str, RunGrant] = {}
        self._audit: list[AccessAuditEvent] = []
        self._locks: dict[str, asyncio.Lock] = {}

    def lock_for(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def get_overlay(self) -> dict[str, Any]:
        return {
            "assignments": dict(self._overlay.get("assignments") or {}),
        }

    async def set_overlay(self, overlay: dict[str, Any]) -> None:
        self._overlay = {
            "assignments": dict(overlay.get("assignments") or {}),
        }

    async def list_requests(self) -> list[ApprovalRequest]:
        return list(self._requests.values())

    async def get_request(self, request_id: str) -> ApprovalRequest | None:
        return self._requests.get(request_id)

    async def save_request(self, request: ApprovalRequest) -> ApprovalRequest:
        self._requests[request.request_id] = request
        return request

    async def list_grants(self) -> list[RunGrant]:
        return list(self._grants.values())

    async def get_grant(self, grant_id: str) -> RunGrant | None:
        return self._grants.get(grant_id)

    async def save_grant(self, grant: RunGrant) -> RunGrant:
        self._grants[grant.grant_id] = grant
        return grant

    async def append_audit(self, event: AccessAuditEvent) -> None:
        self._audit.append(event)
        if len(self._audit) > self.audit_limit:
            self._audit = self._audit[-self.audit_limit :]

    async def list_audit(self, *, limit: int = 50) -> list[AccessAuditEvent]:
        return list(self._audit[-limit:])

    def export_state(self) -> dict[str, Any]:
        return {
            "overlay": {
                "assignments": dict((self._overlay.get("assignments") or {})),
            },
            "requests": {k: v.to_dict() for k, v in self._requests.items()},
            "grants": {k: v.to_dict() for k, v in self._grants.items()},
            "audit": [e.to_dict() for e in self._audit],
        }

    def import_state(self, data: dict[str, Any]) -> None:
        overlay = data.get("overlay") or {}
        self._overlay = {"assignments": dict(overlay.get("assignments") or {})}
        self._requests = {
            k: ApprovalRequest.from_dict(v)
            for k, v in (data.get("requests") or {}).items()
        }
        self._grants = {
            k: RunGrant.from_dict(v) for k, v in (data.get("grants") or {}).items()
        }
        self._audit = [
            AccessAuditEvent.from_dict(e) for e in data.get("audit") or []
        ]


class ImageRetentionStore:
    """Process-local bounded image retention for pending approvals.

    Tradeoff: Discord CDN URLs can expire during the 12h approval window, so we
    download and retain base64 bytes in memory (not Beacon) up to
    ``max_total_bytes``. Expired/denied requests drop their bytes. This avoids
    unbounded Beacon growth and secret-like blob persistence while keeping
    approvals usable after CDN expiry.
    """

    def __init__(self, *, max_total_bytes: int):
        self.max_total_bytes = max_total_bytes
        self._items: dict[str, ImageRetention] = {}
        self._lock = asyncio.Lock()

    @property
    def total_bytes(self) -> int:
        return sum(item.total_bytes for item in self._items.values())

    async def put(
        self,
        request_id: str,
        images: list[ImageInput],
        *,
        expires_at=None,
    ) -> ImageRetention:
        async with self._lock:
            total = 0
            retained: list[ImageInput] = []
            for img in images:
                size = img.size_bytes or (
                    len(img.data_b64) * 3 // 4 if img.data_b64 else 0
                )
                if total + size > self.max_total_bytes:
                    break
                retained.append(img)
                total += size
            item = ImageRetention(
                request_id=request_id,
                images=retained,
                expires_at=expires_at,
                total_bytes=total,
            )
            self._items[request_id] = item
            return item

    async def get(self, request_id: str) -> list[ImageInput] | None:
        async with self._lock:
            item = self._items.get(request_id)
            if item is None:
                return None
            if item.expires_at and utcnow() >= item.expires_at:
                del self._items[request_id]
                return None
            return list(item.images)

    async def discard(self, request_id: str) -> None:
        async with self._lock:
            self._items.pop(request_id, None)

    async def purge_expired(self) -> int:
        async with self._lock:
            now = utcnow()
            dead = [
                rid
                for rid, item in self._items.items()
                if item.expires_at and now >= item.expires_at
            ]
            for rid in dead:
                del self._items[rid]
            return len(dead)


class AccessController:
    """Evaluates tiers and manages approvals/grants."""

    def __init__(
        self,
        config: CursorCloudConfig,
        store: AccessStore,
        *,
        image_retention: ImageRetentionStore | None = None,
    ):
        self.config = config
        self.store = store
        self.images = image_retention or ImageRetentionStore(
            max_total_bytes=config.max_retained_image_bytes
        )

    @property
    def access_config(self) -> AccessConfig:
        return self.config.access

    async def resolve_tier(self, user_id: str | int) -> AccessTier:
        uid = str(user_id)
        if not self.config.god_user_id:
            # Missing/invalid GOD fails closed for everyone.
            return AccessTier.DENIED
        if uid == self.config.god_user_id:
            return AccessTier.GOD

        overlay = await self.store.get_overlay()
        assignments = overlay.get("assignments") or {}
        overlay_value = assignments.get(uid)

        file_tier1 = set(self.access_config.tier1_user_ids)
        file_tier2 = set(self.access_config.tier2_user_ids)

        if overlay_value == "reset":
            # Explicit return to file-config / default.
            if uid in file_tier1:
                return AccessTier.ADMIN
            if uid in file_tier2:
                return AccessTier.APPROVAL
            return AccessTier.DENIED
        if overlay_value == "1":
            return AccessTier.ADMIN
        if overlay_value == "2":
            return AccessTier.APPROVAL
        if overlay_value == "3":
            return AccessTier.DENIED

        if uid in file_tier1:
            return AccessTier.ADMIN
        if uid in file_tier2:
            return AccessTier.APPROVAL
        return AccessTier.DENIED

    async def require_tier(
        self, user_id: str | int, *, minimum: AccessTier = AccessTier.APPROVAL
    ) -> AccessTier:
        tier = await self.resolve_tier(user_id)
        if int(tier) > int(minimum):
            raise AuthorizationError()
        return tier

    async def require_approver(self, user_id: str | int) -> AccessTier:
        tier = await self.resolve_tier(user_id)
        if tier not in {AccessTier.GOD, AccessTier.ADMIN}:
            raise AuthorizationError(
                user_message="Only God or Tier 1 admins can approve Cursor runs."
            )
        return tier

    async def require_god(self, user_id: str | int) -> None:
        tier = await self.resolve_tier(user_id)
        if tier != AccessTier.GOD:
            raise AuthorizationError(
                user_message="Only God can manage Cursor access tiers."
            )

    async def can_use_command(self, user_id: str | int, command: str) -> bool:
        tier = await self.resolve_tier(user_id)
        if tier == AccessTier.DENIED:
            return False
        if tier in {AccessTier.GOD, AccessTier.ADMIN}:
            return True
        # Tier 2
        allowed = {
            "run",
            "stop",
            "sessions",
            "session",
            "model",
            "status",
            "approve",
            "deny",
        }
        # Tier 2 cannot use access management; approve/deny still gated by require_approver.
        if command.startswith("access"):
            return False
        if command in {"approve", "deny"}:
            return False
        return command in allowed

    async def set_user_tier(
        self, actor_id: str | int, target_id: str | int, tier: int | str
    ) -> AccessTier:
        await self.require_god(actor_id)
        target = str(target_id)
        if not target.isdigit():
            raise ValidationError(
                "Invalid target id",
                user_message="Target must be a Discord user ID.",
            )
        if target == self.config.god_user_id:
            raise ValidationError(
                "Cannot change God tier",
                user_message="Tier 0 (God) cannot be changed via commands.",
            )

        if str(tier).lower() in {"reset", "default", "file"}:
            new_value = "reset"
            resulting = await self._file_tier(target)
        else:
            tier_int = int(tier)
            if tier_int not in (1, 2, 3):
                raise ValidationError(
                    "Invalid tier",
                    user_message="Assignable tiers are 1, 2, 3, or reset.",
                )
            new_value = str(tier_int)
            resulting = AccessTier(tier_int)

        previous = await self.resolve_tier(target)
        overlay = await self.store.get_overlay()
        assignments = dict(overlay.get("assignments") or {})
        assignments[target] = new_value
        await self.store.set_overlay({"assignments": assignments})
        await self._audit(
            actor_id,
            "set_tier",
            target_id=target,
            detail={"previous": int(previous), "new": int(resulting), "overlay": new_value},
        )
        return resulting

    async def _file_tier(self, user_id: str) -> AccessTier:
        if user_id in self.access_config.tier1_user_ids:
            return AccessTier.ADMIN
        if user_id in self.access_config.tier2_user_ids:
            return AccessTier.APPROVAL
        return AccessTier.DENIED

    async def list_assignments(self) -> dict[str, Any]:
        overlay = await self.store.get_overlay()
        return {
            "god": self.config.god_user_id,
            "file_tier1": list(self.access_config.tier1_user_ids),
            "file_tier2": list(self.access_config.tier2_user_ids),
            "overlay": dict(overlay.get("assignments") or {}),
        }

    async def current_approver_ids(self) -> list[str]:
        ids: list[str] = []
        if self.config.god_user_id:
            ids.append(self.config.god_user_id)
        # Include effective Tier 1 users (file + overlay).
        candidates = set(self.access_config.tier1_user_ids)
        overlay = await self.store.get_overlay()
        for uid, value in (overlay.get("assignments") or {}).items():
            if value == "1":
                candidates.add(uid)
            elif value in {"2", "3", "reset"} and uid in candidates:
                # May still be tier1 via file if reset; handled below.
                pass
        for uid in sorted(candidates):
            if await self.resolve_tier(uid) == AccessTier.ADMIN and uid not in ids:
                ids.append(uid)
        return ids

    async def create_approval_request(
        self,
        envelope: RunRequestEnvelope,
        *,
        prompt_preview: str,
        images: list[ImageInput] | None = None,
    ) -> ApprovalRequest:
        now = utcnow()
        expires = now + timedelta(hours=self.access_config.approval_timeout_hours)
        request = ApprovalRequest(
            request_id=new_id("apr"),
            envelope_hash=envelope_hash(envelope),
            envelope=envelope,
            decision=ApprovalDecision.PENDING,
            created_at=now,
            expires_at=expires,
            prompt_preview=prompt_preview[:400],
        )
        await self.store.save_request(request)
        if images:
            await self.images.put(request.request_id, images, expires_at=expires)
        await self._audit(
            envelope.requester_id,
            "approval_created",
            target_id=request.request_id,
            detail={"hash": request.envelope_hash, "scope": envelope.scope.to_dict()},
        )
        return request

    async def expire_stale_requests(self) -> list[ApprovalRequest]:
        now = utcnow()
        expired: list[ApprovalRequest] = []
        for request in await self.store.list_requests():
            if request.decision != ApprovalDecision.PENDING:
                continue
            if request.expires_at and now >= request.expires_at:
                request.decision = ApprovalDecision.EXPIRED
                request.decided_at = now
                await self.store.save_request(request)
                await self.images.discard(request.request_id)
                expired.append(request)
        await self.images.purge_expired()
        return expired

    async def decide_request(
        self,
        actor_id: str | int,
        request_id: str,
        *,
        mode: str,
        minutes: int | None = None,
    ) -> ApprovalRequest:
        await self.require_approver(actor_id)
        lock = self.store.lock_for(f"request:{request_id}")
        async with lock:
            request = await self.store.get_request(request_id)
            if request is None:
                raise StaleStateError(user_message="Approval request not found.")
            now = utcnow()
            if request.decision != ApprovalDecision.PENDING:
                raise StaleStateError(
                    user_message=f"Request already {request.decision.value}."
                )
            if request.expires_at and now >= request.expires_at:
                request.decision = ApprovalDecision.EXPIRED
                request.decided_at = now
                await self.store.save_request(request)
                await self.images.discard(request.request_id)
                raise StaleStateError(user_message="Approval request expired.")

            mode_norm = str(mode).lower().strip()
            if mode_norm in {"deny", "denied"}:
                request.decision = ApprovalDecision.DENIED
                request.decided_at = now
                request.decided_by = str(actor_id)
                await self.store.save_request(request)
                await self.images.discard(request.request_id)
                await self._audit(
                    actor_id,
                    "approval_denied",
                    target_id=request_id,
                    detail={},
                )
                return request

            if mode_norm in {"once", "approve_once", "one"}:
                grant = RunGrant(
                    grant_id=new_id("gr"),
                    scope=request.envelope.scope,
                    user_id=request.envelope.requester_id,
                    kind="once",
                    created_at=now,
                    envelope_hash=request.envelope_hash,
                    request_id=request.request_id,
                    created_by=str(actor_id),
                )
                await self.store.save_grant(grant)
                request.decision = ApprovalDecision.APPROVED_ONCE
                request.grant_id = grant.grant_id
                request.decided_at = now
                request.decided_by = str(actor_id)
                await self.store.save_request(request)
                await self._audit(
                    actor_id,
                    "approval_once",
                    target_id=request_id,
                    detail={"grant_id": grant.grant_id},
                )
                return request

            if mode_norm in {"timed", "approve_timed", "time", "minutes"}:
                mins = self.access_config.clamp_grant_minutes(minutes)
                grant = RunGrant(
                    grant_id=new_id("gr"),
                    scope=request.envelope.scope,
                    user_id=request.envelope.requester_id,
                    kind="timed",
                    created_at=now,
                    expires_at=now + timedelta(minutes=mins),
                    request_id=request.request_id,
                    created_by=str(actor_id),
                )
                await self.store.save_grant(grant)
                request.decision = ApprovalDecision.APPROVED_TIMED
                request.grant_id = grant.grant_id
                request.grant_minutes = mins
                request.decided_at = now
                request.decided_by = str(actor_id)
                await self.store.save_request(request)
                await self._audit(
                    actor_id,
                    "approval_timed",
                    target_id=request_id,
                    detail={"grant_id": grant.grant_id, "minutes": mins},
                )
                return request

            raise ValidationError(
                f"Unknown approval mode {mode}",
                user_message="Use once, timed, or deny.",
            )

    async def find_valid_grant(
        self, scope: ScopeKey, user_id: str, envelope: RunRequestEnvelope
    ) -> RunGrant | None:
        now = utcnow()
        digest = envelope_hash(envelope)
        for grant in await self.store.list_grants():
            if grant.revoked or grant.consumed:
                continue
            if grant.user_id != str(user_id):
                continue
            if grant.scope.as_str() != scope.as_str():
                continue
            if grant.kind == "timed":
                if grant.expires_at and now < grant.expires_at:
                    return grant
                continue
            if grant.kind == "once" and grant.envelope_hash == digest:
                return grant
        return None

    async def consume_grant_for_submit(
        self, grant: RunGrant, envelope: RunRequestEnvelope
    ) -> RunGrant:
        """Atomically consume a one-run grant before API submit.

        Timed grants are not consumed. If API submit fails after one-run
        consumption, callers must surface GrantConsumedError and must not
        restore the grant.
        """
        lock = self.store.lock_for(f"grant:{grant.grant_id}")
        async with lock:
            current = await self.store.get_grant(grant.grant_id)
            if current is None or current.revoked:
                raise StaleStateError(user_message="Grant is no longer valid.")
            if current.kind == "timed":
                if current.expires_at and utcnow() >= current.expires_at:
                    raise StaleStateError(user_message="Timed grant expired.")
                return current
            if current.consumed:
                raise StaleStateError(user_message="One-run grant already used.")
            if current.envelope_hash != envelope_hash(envelope):
                raise StaleStateError(
                    user_message="Grant does not match this exact request."
                )
            current.consumed = True
            await self.store.save_grant(current)
            if current.request_id:
                request = await self.store.get_request(current.request_id)
                if request and request.decision == ApprovalDecision.APPROVED_ONCE:
                    request.decision = ApprovalDecision.CONSUMED
                    await self.store.save_request(request)
            await self._audit(
                current.user_id,
                "grant_consumed",
                target_id=current.grant_id,
                detail={"request_id": current.request_id},
            )
            return current

    async def mark_submit_failed_after_consume(self, grant: RunGrant) -> None:
        """Fail-closed: leave grant consumed; discard retained images."""
        if grant.request_id:
            await self.images.discard(grant.request_id)
        await self._audit(
            grant.user_id,
            "submit_failed_after_consume",
            target_id=grant.grant_id,
            detail={"request_id": grant.request_id},
        )

    def raise_submit_failed(self, grant: RunGrant, cause: Exception) -> None:
        raise GrantConsumedError(str(cause)) from cause

    async def revoke_grant(self, actor_id: str | int, grant_id: str) -> RunGrant:
        await self.require_god(actor_id)
        grant = await self.store.get_grant(grant_id)
        if grant is None:
            raise StaleStateError(user_message="Grant not found.")
        grant.revoked = True
        await self.store.save_grant(grant)
        await self._audit(
            actor_id, "grant_revoked", target_id=grant_id, detail={}
        )
        return grant

    async def authorization_for_run(
        self, user_id: str | int, scope: ScopeKey, envelope: RunRequestEnvelope
    ) -> tuple[AccessTier, RunGrant | None, ApprovalRequest | None]:
        """Return (tier, usable_grant, created_pending_request).

        For Tier 2 without grant, does not create a request — caller creates it
        after idle/model decisions. This helper only looks up grants.
        """
        tier = await self.resolve_tier(user_id)
        if tier == AccessTier.DENIED:
            raise AuthorizationError()
        if tier in {AccessTier.GOD, AccessTier.ADMIN}:
            return tier, None, None
        grant = await self.find_valid_grant(scope, str(user_id), envelope)
        return tier, grant, None

    async def _audit(
        self,
        actor_id: str | int,
        action: str,
        *,
        target_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        event = AccessAuditEvent(
            event_id=new_id("aud"),
            actor_id=str(actor_id),
            action=action,
            target_id=target_id,
            detail=detail or {},
        )
        await self.store.append_audit(event)


def redact_preview(text: str, *, limit: int = 240) -> str:
    cleaned = (text or "").replace("@everyone", "@\u200beveryone").replace(
        "@here", "@\u200bhere"
    )
    # Neutralize user/role mention forms without removing readability entirely.
    cleaned = cleaned.replace("<@", "<\u200b@")
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"
