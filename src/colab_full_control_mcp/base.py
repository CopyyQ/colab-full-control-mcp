from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from .audit import AuditLogger
from .auth import AuthManager
from .common import MCPToolError, ToolRunContext, error_response, make_request_id, ok_response
from .permissions import PermissionManager, PermissionProfile
from .settings import Settings


@dataclass(slots=True)
class ToolPayload:
    data: dict[str, Any]
    message: str = "OK"
    truncated: bool = False


class BaseToolset:
    def __init__(
        self,
        *,
        settings: Settings,
        auth_manager: AuthManager,
        permission_manager: PermissionManager,
        audit_logger: AuditLogger,
    ):
        self.settings = settings
        self.auth_manager = auth_manager
        self.permission_manager = permission_manager
        self.audit_logger = audit_logger

    def _invoke(
        self,
        *,
        tool_name: str,
        action_category: str,
        operation: Callable[[], dict[str, Any] | ToolPayload],
        min_profile: PermissionProfile = PermissionProfile.READ_ONLY,
        token: str | None = None,
        confirm: bool = False,
        destructive: bool = False,
        require_token: bool | None = None,
        args: dict[str, Any] | None = None,
        paths: list[str] | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        request_id = make_request_id()
        started = time.perf_counter()
        try:
            token_needed = require_token if require_token is not None else min_profile > PermissionProfile.READ_ONLY
            if token_needed:
                self.auth_manager.require_token(token)
            self.permission_manager.require(min_profile)
            if destructive:
                self.permission_manager.require_confirm(confirm)

            result = operation()
            payload = result if isinstance(result, ToolPayload) else ToolPayload(data=result)
            duration_ms = int((time.perf_counter() - started) * 1000)
            self.audit_logger.write(
                request_id=request_id,
                tool=tool_name,
                action_category=action_category,
                args=args,
                paths=paths,
                job_id=job_id,
                duration_ms=duration_ms,
                success=True,
            )
            return ok_response(
                payload.data,
                message=payload.message,
                request_id=request_id,
                truncated=payload.truncated,
            )
        except MCPToolError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            self.audit_logger.write(
                request_id=request_id,
                tool=tool_name,
                action_category=action_category,
                args=args,
                paths=paths,
                job_id=job_id,
                duration_ms=duration_ms,
                success=False,
                error=str(exc),
            )
            return exc.to_response(request_id=request_id)
        except Exception as exc:  # pragma: no cover - defensive boundary
            duration_ms = int((time.perf_counter() - started) * 1000)
            self.audit_logger.write(
                request_id=request_id,
                tool=tool_name,
                action_category=action_category,
                args=args,
                paths=paths,
                job_id=job_id,
                duration_ms=duration_ms,
                success=False,
                error=str(exc),
            )
            return error_response("internal_error", str(exc), request_id=request_id)

    def _ctx(self, tool_name: str, action_category: str) -> ToolRunContext:
        return ToolRunContext(tool_name=tool_name, request_id=make_request_id(), action_category=action_category)

