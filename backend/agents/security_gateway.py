from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar, Any
from collections import OrderedDict

from backend.security.audit import AuditLogger
from backend.security.authorization import AuthorizationService, Permission, Resource, UserAttributes
from backend.security.ai.limits import ToolCallBudget, ToolCallLimitExceeded
from backend.security.ai.output_guard import SensitiveDataFilter
from backend.security.ai.tool_policy import ToolAllowlist
from backend.observability.logging import log_event
import logging
import time

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ToolPolicyDenied(PermissionError):
    pass


class ToolExecutionTimeout(TimeoutError):
    pass


@dataclass
class ToolContext:
    """Non-secret context passed to capability execution."""
    request_id: str
    user: UserAttributes
    budget: ToolCallBudget | None = None


class SecureToolGateway(Generic[T]):
    """Mandatory security boundary: allowlist -> auth -> policy -> budget -> execution -> output validation -> audit."""
    def __init__(self, authorization: AuthorizationService, audit: AuditLogger,
                 allowlist: ToolAllowlist | None = None, max_tool_calls: int = 8,
                 execution_timeout_seconds: float = 10.0,
                 output_filter: SensitiveDataFilter | None = None) -> None:
        self._authorization = authorization
        self._audit = audit
        self._allowlist = allowlist or ToolAllowlist()
        if max_tool_calls <= 0:
            raise ValueError("max_tool_calls must be positive")
        self._max_tool_calls = max_tool_calls
        self._budgets: OrderedDict[tuple[str, str, str], ToolCallBudget] = OrderedDict()
        self._max_budget_contexts = 10000
        if execution_timeout_seconds <= 0:
            raise ValueError("execution_timeout_seconds must be positive")
        self._timeout = execution_timeout_seconds
        self._output_filter = output_filter or SensitiveDataFilter()

    def execute(
        self,
        context: ToolContext,
        capability: str,
        permission: Permission,
        resource: Resource,
        operation: Callable[[], T],
        policy: Callable[[], bool] | None = None,
        *,
        input_validator: Callable[[], None] | None = None,
        output_validator: Callable[[T], T] | None = None,
    ) -> T:
        started = time.perf_counter()
        log_event(logger, "tool_execution_started", actor_id=context.user.user_id, tenant_id=context.user.tenant_id,
                  capability=capability, permission=permission.value, resource_id=resource.resource_id,
                  request_id=context.request_id)
        configured = self._allowlist.get(capability)
        if not configured or not configured.enabled:
            self._deny(context, resource, capability, "Tool is not on the allowlist")
        if permission not in configured.permissions:
            self._deny(context, resource, capability, "Tool permission does not match allowlist")
        try:
            if context.budget is None:
                key = (context.user.tenant_id, context.user.user_id, context.request_id)
                budget = self._budgets.get(key)
                if budget is None:
                    budget = ToolCallBudget(max_calls=self._max_tool_calls)
                    self._budgets[key] = budget
                    self._budgets.move_to_end(key)
                    while len(self._budgets) > self._max_budget_contexts:
                        self._budgets.popitem(last=False)
                context.budget = budget
            context.budget.consume()
        except ToolCallLimitExceeded as exc:
            self._audit.record("tool_call_budget", "deny", context.user.user_id, context.user.tenant_id,
                               resource.resource_id, {"capability": capability})
            raise ToolPolicyDenied("Tool-call budget exceeded") from exc
        decision = self._authorization.authorize(context.user, permission, resource)
        if not decision.allowed:
            self._deny(context, resource, capability, decision.reason)
        if input_validator is not None:
            try:
                input_validator()
            except Exception as exc:
                self._audit.record("tool_input_validation", "deny", context.user.user_id, context.user.tenant_id,
                                   resource.resource_id, {"capability": capability})
                raise ToolPolicyDenied("Tool input validation failed") from exc
        if policy is not None and not policy():
            self._deny(context, resource, capability, "Policy validation failed")
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nanvi-tool")
        future = executor.submit(operation)
        try:
            result = future.result(timeout=self._timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            log_event(logger, "tool_execution_failed", logging.ERROR, actor_id=context.user.user_id, tenant_id=context.user.tenant_id,
                      capability=capability, resource_id=resource.resource_id, outcome="timeout", duration_ms=duration_ms)
            self._audit.record("tool_execution", "timeout", context.user.user_id, context.user.tenant_id,
                               resource.resource_id, {"capability": capability, "timeout_seconds": self._timeout, "duration_ms": duration_ms})
            raise ToolExecutionTimeout("Tool execution timed out") from exc
        except Exception as exc:
            executor.shutdown(wait=True, cancel_futures=True)
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            log_event(logger, "tool_execution_failed", logging.ERROR, actor_id=context.user.user_id, tenant_id=context.user.tenant_id,
                      capability=capability, resource_id=resource.resource_id, outcome="error", duration_ms=duration_ms,
                      exception_type=type(exc).__name__)
            self._audit.record("tool_execution", "error", context.user.user_id, context.user.tenant_id,
                               resource.resource_id, {"capability": capability, "duration_ms": duration_ms})
            raise
        else:
            executor.shutdown(wait=True, cancel_futures=True)
        if output_validator is not None:
            result = output_validator(result)
        # Never let raw tool outputs accidentally expose obvious secrets/paths/SQL.
        # Structured internal objects should normally be converted to a safe response model first.
        # Apply the public-output filter to structured results as well; otherwise
        # secrets nested in dict/list tool responses could bypass the string-only check.
        result = self._output_filter.validate_public_output(result)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        log_event(logger, "tool_execution_completed", actor_id=context.user.user_id, tenant_id=context.user.tenant_id,
                  capability=capability, resource_id=resource.resource_id, outcome="allow", duration_ms=duration_ms)
        self._audit.record("tool_execution", "allow", context.user.user_id, context.user.tenant_id,
                           resource.resource_id, {"capability": capability, "duration_ms": duration_ms})
        return result

    def _deny(self, context: ToolContext, resource: Resource, capability: str, reason: str) -> None:
        log_event(logger, "tool_execution_denied", logging.WARNING, actor_id=context.user.user_id, tenant_id=context.user.tenant_id,
                  capability=capability, resource_id=resource.resource_id, reason=reason)
        self._audit.record("tool_execution", "deny", context.user.user_id, context.user.tenant_id,
                           resource.resource_id, {"request_id": context.request_id, "capability": capability, "reason": reason})
        raise ToolPolicyDenied("Tool request denied")
