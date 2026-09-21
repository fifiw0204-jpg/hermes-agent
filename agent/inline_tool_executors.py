"""Agent-level ("inline") tool executors shared by the sequential and concurrent tool paths.

These tools need live ``AIAgent`` state (stores, callbacks, session DB) and therefore
bypass the tool registry. Each executor is ``fn(agent, args, ctx) -> result``; the
table replaces two hand-maintained if/elif chains (``invoke_tool`` and
``execute_tool_calls_sequential``) that had drifted apart. Tool modules are imported
lazily at call time so ``patch("tools.x.y")`` in tests keeps working.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable, Dict, Optional, Tuple


def tool_hook_ids(agent, effective_task_id: str, tool_call_id: Optional[str]) -> Dict[str, str]:
    """Identity kwargs every tool hook/middleware call carries (all coerced to ``""``)."""
    return {
        "task_id": effective_task_id or "",
        "session_id": getattr(agent, "session_id", "") or "",
        "tool_call_id": tool_call_id or "",
        "turn_id": getattr(agent, "_current_turn_id", "") or "",
        "api_request_id": getattr(agent, "_current_api_request_id", "") or "",
    }


def emit_terminal_post_tool_call(
    agent,
    *,
    function_name: str,
    function_args: dict,
    result: Any,
    effective_task_id: str,
    tool_call_id: Optional[str],
    duration_ms: int = 0,
    status: Optional[str] = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    middleware_trace: Optional[list] = None,
) -> None:
    """Emit the one terminal ``post_tool_call`` hook for a tool_call_id (best-effort)."""
    try:
        from model_tools import _emit_post_tool_call_hook
        _emit_post_tool_call_hook(
            function_name=function_name,
            function_args=function_args,
            result=result,
            **tool_hook_ids(agent, effective_task_id, tool_call_id),
            duration_ms=duration_ms,
            status=status,
            error_type=error_type,
            error_message=error_message,
            middleware_trace=list(middleware_trace or []),
        )
    except Exception:
        pass


@dataclass
class InlineToolContext:
    """Per-call state an inline executor may need beyond its arguments."""

    effective_task_id: str
    tool_call_id: Optional[str] = None
    messages: Optional[list] = None


InlineToolExecutor = Callable[[Any, dict, InlineToolContext], Any]

# ``(kwarg, args_key)`` → ``args.get(key)``; ``(kwarg, args_key, default)`` → ``args.get(key, default)``.
_ArgSpec = Tuple[Any, ...]


def _call_tool(module: str, func: str, args: dict, arg_specs: Tuple[_ArgSpec, ...], **fixed: Any) -> Any:
    """Import ``module.func`` lazily and call it with args mapped per ``arg_specs`` plus ``fixed``."""
    fn = getattr(import_module(module), func)
    return fn(**{spec[0]: args.get(*spec[1:]) for spec in arg_specs}, **fixed)


def _tool(
    module: str, func: str, *arg_specs: _ArgSpec, **fixed: Callable[[Any, InlineToolContext], Any],
) -> InlineToolExecutor:
    """Executor calling ``module.func`` with mapped args plus ``fixed`` kwargs computed from ``(agent, ctx)``."""
    def _exec(agent, args: dict, ctx: InlineToolContext) -> Any:
        return _call_tool(module, func, args, arg_specs, **{k: f(agent, ctx) for k, f in fixed.items()})
    return _exec


def _callback_tool(module: str, func: str, callback_attr: str, *arg_specs: _ArgSpec) -> InlineToolExecutor:
    """Executor for a GUI-callback tool: mapped args plus ``callback=getattr(agent, callback_attr, None)``."""
    return _tool(module, func, *arg_specs, callback=lambda agent, ctx: getattr(agent, callback_attr, None))


def _session_search(agent, args: dict, ctx: InlineToolContext) -> Any:
    session_db = agent._get_session_db_for_recall()
    if not session_db:
        from hermes_state import format_session_db_unavailable

        return json.dumps({"success": False, "error": format_session_db_unavailable()})
    return _call_tool(
        "tools.session_search_tool", "session_search", args,
        (
            ("query", "query", ""), ("role_filter", "role_filter"), ("limit", "limit", 3),
            ("session_id", "session_id"), ("around_message_id", "around_message_id"),
            ("window", "window", 5), ("sort", "sort"), ("detail", "detail", "adaptive"),
        ),
        db=session_db, current_session_id=agent.session_id,
    )


def _memory(agent, args: dict, ctx: InlineToolContext) -> Any:
    result = _call_tool(
        "tools.memory_tool", "memory_tool", args,
        (
            ("action", "action"), ("target", "target", "memory"), ("content", "content"),
            ("old_text", "old_text"), ("new_text", "new_text"), ("operations", "operations"),
        ),
        store=agent._memory_store,
    )
    # Mirror built-in memory writes to external providers; gating lives in
    # MemoryManager.notify_memory_tool_write.
    if agent._memory_manager:
        agent._memory_manager.notify_memory_tool_write(
            result,
            args,
            build_metadata=lambda: agent._build_memory_write_metadata(
                task_id=ctx.effective_task_id,
                tool_call_id=ctx.tool_call_id,
            ),
        )
    return result


_read_preview = _callback_tool(
    "tools.read_preview_tool", "read_preview_tool", "read_preview_callback",
    ("start", "start"), ("count", "count"),
)


def _desktop_preview(agent, args: dict, ctx: InlineToolContext) -> Any:
    # action=read needs the GUI callback (agent-level); open/close go through the
    # registry handler like any other tool.
    if (args.get("action") or "").strip() == "read":
        return _read_preview(agent, args, ctx)
    from tools.preview_tool import _handle_preview

    return _handle_preview(args)


def _manage_connections(agent, args: dict, ctx: InlineToolContext) -> Any:
    # The GUI callback lives on the agent; registry dispatch never forwards it.
    from tools.connectors import manage_connections
    from tools.connectors.gateway import config as gateway_config

    return manage_connections(
        args, session_id=getattr(agent, "session_id", None), tool_call_id=ctx.tool_call_id,
        connection_callback=getattr(agent, "connection_callback", None),
        connectors_available=gateway_config.connectors_available,
    )


def _setup_mcp_shim(agent, args: dict, ctx: InlineToolContext) -> Any:
    # Replay shim for conversations whose cached prompt still names setup_mcp.
    # Not in _LEGACY_TOOL_ALIASES: inline tools bypass handle_function_call.
    return _manage_connections(agent, {
        "action": args.get("action", "install"),
        "connectors": [{"name": args.get("server", ""), "mcp": True}],
    }, ctx)


def _chitchat_kanban_create(agent, args: dict, ctx: InlineToolContext) -> Any:
    """Auto-fill kanban_create title from pending chitchat intent when user confirmed 'yes'.

    Fires when the model calls ``kanban_create`` after the user confirmed the chitchat
    intent prompt.
    """
    from agent.chitchat_kanban_flow import chitchat_kanban_confirmed_intent

    pending = chitchat_kanban_confirmed_intent(agent)
    if pending:
        if not args.get("title"):
            user_msg = pending.get("user_message", "")[:100]
            args = dict(args)
            args["title"] = f"[chitchat] {user_msg}"

    # Pass task_id as part of args dict so _handle_create receives it via **kw,
    # not as a separate fixed= keyword arg that _call_tool can't route correctly.
    args["task_id"] = ctx.effective_task_id
    return _call_tool(
        "tools.kanban_tools", "_handle_create", args,
        (
            ("title", "title"), ("body", "body"), ("assignee", "assignee"),
            ("parent", "parent"), ("parents", "parents"), ("priority", "priority"),
            ("board", "board"), ("workspace_kind", "workspace_kind"),
            ("workspace_path", "workspace_path"), ("project", "project"),
            ("skills", "skills"), ("goal_mode", "goal_mode"),
            ("model", "model"), ("provider", "provider"),
            ("max_runtime_seconds", "max_runtime_seconds"),
            ("completion_contract", "completion_contract"),
            ("initial_status", "initial_status"),
        ),
    )


def _direct_kanban_create(agent, args: dict, ctx: InlineToolContext) -> Any:
    """Direct kanban task creation for non-chitchat (task-worthy) user messages.

    Triggered by finish_text_response when chitchat_kanban_check returns
    direct_register=True.  The message body carries the original user text.
    The title is the first 100 chars of the user message.
    """
    msg = getattr(agent, "_last_direct_register_message", "") or ""
    title = msg[:100] if msg else "Untitled task"
    body = msg

    resolved_args = {
        "title": args.get("title") or title,
        "body": args.get("body") or body,
        "assignee": args.get("assignee") or "",
        "priority": args.get("priority") or 0,
        "workspace_kind": args.get("workspace_kind") or "",
        "workspace_path": args.get("workspace_path") or "",
        "completion_contract": args.get("completion_contract") or "",
    }
    # Apply any explicit overrides passed by the model call.
    for key in ("title", "body", "assignee", "priority",
                "workspace_kind", "workspace_path", "completion_contract",
                "parent", "parents", "board", "project",
                "skills", "goal_mode", "model", "provider",
                "max_runtime_seconds", "initial_status"):
        if key in args:
            resolved_args[key] = args[key]

    resolved_args["task_id"] = ctx.effective_task_id
    return _call_tool(
        "tools.kanban_tools", "_handle_create", resolved_args,
        (
            ("title", "title"), ("body", "body"), ("assignee", "assignee"),
            ("parent", "parent"), ("parents", "parents"), ("priority", "priority"),
            ("board", "board"), ("workspace_kind", "workspace_kind"),
            ("workspace_path", "workspace_path"), ("project", "project"),
            ("skills", "skills"), ("goal_mode", "goal_mode"),
            ("model", "model"), ("provider", "provider"),
            ("max_runtime_seconds", "max_runtime_seconds"),
            ("completion_contract", "completion_contract"),
            ("initial_status", "initial_status"),
        ),
    )
# Order is the historical if/elif order of ``execute_tool_calls_sequential``.
INLINE_TOOL_EXECUTORS: Dict[str, InlineToolExecutor] = {
    "todo_list": _tool(
        "tools.todo_tool", "todo_tool", ("todos", "todos"), ("merge", "merge", False),
        store=lambda agent, ctx: agent._todo_store,
    ),
    # Bot Mode teammate DM is injected, not registered: only a canonical Bot
    # Chat session carries the schema, and the tool re-gates on the title.
    "message_agent": _tool(
        "tools.bot_mode_dm", "message_agent_tool", ("target", "target", ""), ("message", "message", ""),
        task_id=lambda agent, ctx: ctx.effective_task_id, agent=lambda agent, ctx: agent,
    ),
    "session_search": _session_search,
    "memory": _memory,
    "clarify": _tool(
        "tools.clarify_tool", "clarify_tool",
        ("question", "question", ""), ("choices", "choices"), ("multi_select", "multi_select", False),
        ("questions", "questions"),
        callback=lambda agent, ctx: agent.clarify_callback,
    ),
    "read_terminal": _callback_tool(
        "tools.read_terminal_tool", "read_terminal_tool", "read_terminal_callback",
        ("start_line", "start_line"), ("count", "count"),
    ),
    "desktop_preview": _desktop_preview,
    "drive_preview": _callback_tool(
        "tools.drive_preview_tool", "drive_preview_tool", "drive_preview_callback",
        ("action", "action", ""), ("ref", "ref"), ("selector", "selector"), ("text", "text"),
        ("key", "key"), ("submit", "submit"), ("amount", "amount"), ("to", "to"), ("limit", "max"),
    ),
    "annotate_preview": _callback_tool(
        "tools.annotate_preview_tool", "annotate_preview_tool", "drive_preview_callback",
        ("action", "action", "add"), ("ref", "ref"), ("selector", "selector"), ("label", "label"),
    ),
    "read_window_below": _callback_tool(
        "tools.read_window_tool", "read_window_below_tool", "read_window_below_callback",
    ),
    "gui_tour": _callback_tool(
        "tools.tour_tool", "tour_tool", "tour_callback",
        ("action", "action", ""), ("surface", "surface"), ("selector", "selector"), ("title", "title"),
        ("text", "text"), ("side", "side"), ("steps", "steps"), ("step_index", "step_index"),
    ),
    "setup_mcp": _callback_tool(
        "tools.setup_mcp_tool", "setup_mcp_tool", "setup_mcp_callback",
        ("server", "server", ""), ("action", "action", "install"), ("reason", "reason", ""),
    ),
    "delegate_task": lambda agent, args, ctx: agent._dispatch_delegate_task(args),
}


# ``invoke_tool`` (concurrent path) consults the memory manager right after these three
# names and before the remaining inline tools; ``message_agent`` falls through to the
# registry there (Bot Mode DM is only injected into the sequential path's schema).
INVOKE_TOOL_PRE_MEMORY_MANAGER_NAMES = frozenset({"todo_list", "session_search", "memory"})


def resolve_invoke_tool_executor(agent, function_name: str) -> Optional[InlineToolExecutor]:
    """Inline executor for ``invoke_tool`` (concurrent path), or None for registry dispatch.

    Precedence: todo_list/session_search/memory, then memory-manager tools, then the
    remaining inline tools (``message_agent`` excluded).
    """
    if function_name in INVOKE_TOOL_PRE_MEMORY_MANAGER_NAMES:
        return INLINE_TOOL_EXECUTORS[function_name]
    memory_manager = agent._memory_manager
    if memory_manager and memory_manager.has_tool(function_name):
        return lambda agent, args, ctx: agent._memory_manager.handle_tool_call(function_name, args)
    if function_name == "message_agent":
        return None
    return INLINE_TOOL_EXECUTORS.get(function_name)
