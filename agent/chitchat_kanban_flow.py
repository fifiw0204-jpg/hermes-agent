"""Chitchat-aware kanban task registration flow.

Implements the flow described in SKILL task t_0fa1633b:

  1. Incoming user message → is_chitchat(message)
  2. If chitchat:
     a. Monitor the ongoing conversation for task-like intent
     b. If intent detected after >= 1 chitchat exchange → inject confirmation prompt
     c. On 'yes' confirmation → trigger kanban task registration
  3. Debouncing: same inferred intent is only prompted once per session

The confirmation prompt "是否要將這個登記為 task？" is injected by the caller
(agent/turn_final_response.py) via the ``chitchat_kanban_*`` agent attributes
set by this module.

Usage in conversation loop (agent/turn_final_response.py):

  from agent.chitchat_kanban_flow import chitchat_kanban_check

  # After a turn's final response is assembled (in finish_text_response):
  verdict = chitchat_kanban_check(
      agent=agent,
      user_message=user_message,
      assistant_response=assistant_response,
      conversation_history=messages,
  )
  if verdict.prompt_requested:
      # Caller injects the confirmation prompt before returning the response
      verdict.inject_confirmation(assistant_response)

The flow is session-level: state is stored on the ``agent`` instance as
ephemeral attributes (``_chitchat_seen``, ``_chitchat_pending_intent``,
``_chitchat_prompted_intents``).
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Optional

from agent.chitchat_classifier import is_chitchat
from agent.chitchat_intent_detector import detect_tasklike_intent_sync

logger = logging.getLogger("agent.chitchat_kanban_flow")

# Confirmation prompt shown to user when intent is detected after chitchat.
CHITCHAT_CONFIRMATION_PROMPT = (
    "\n\n是否要將這個登記為 task？ (yes/no)\n"
    "例如：yes → 建立 kanban task。no → 繼續普通對話。\n"
    "輸入 yes 確認，或 no 取消。"
)

# Keywords that indicate a 'yes' confirmation (any language).
_YES_PATTERN = re.compile(
    r"(?i)^\s*(yes|yep|yeah|ok|okay|sure|好|是|對|對的|好|登記|寫成task|建任務)",
)


@dataclass
class ChitchatKanbanVerdict:
    """Result of ``chitchat_kanban_check``."""

    # True when the confirmation prompt should be injected into the response.
    # The caller appends CHITCHAT_CONFIRMATION_PROMPT to assistant_response
    # and sets agent._chitchat_awaiting_confirmation = True.
    prompt_requested: bool = False

    # The modified response (original + confirmation prompt) — ready to use.
    response_with_prompt: str | None = None

    # Short tag describing why intent was detected (for logging/debugging).
    intent_reason: str = ""

    # Hash of the inferred intent content — used for debouncing.
    # The caller stores this in agent._chitchat_prompted_intents after
    # a prompt is shown, so the same intent is not prompted again.
    intent_hash: str | None = None

    def inject_confirmation(self, base_response: str) -> str:
        """Return base_response with the confirmation prompt appended."""
        return base_response + CHITCHAT_CONFIRMATION_PROMPT


def _intent_hash(user_message: str, intent_reason: str) -> str:
    """Stable hash of (user_message, intent_reason) for debounce tracking."""
    return hashlib.sha256(f"{user_message[:200]}::{intent_reason}".encode()).hexdigest()[:16]


def _is_yes_confirmation(text: str) -> bool:
    """Return True if text is an affirmative confirmation."""
    return bool(_YES_PATTERN.match(text or ""))


def _init_chitchat_state(agent) -> None:
    """Initialise or verify chitchat state attributes on the agent instance."""
    if not hasattr(agent, "_chitchat_seen"):
        agent._chitchat_seen = False
    if not hasattr(agent, "_chitchat_awaiting_confirmation"):
        agent._chitchat_awaiting_confirmation = False
    if not hasattr(agent, "_chitchat_pending_intent"):
        agent._chitchat_pending_intent = None
    if not hasattr(agent, "_chitchat_prompted_intents"):
        agent._chitchat_prompted_intents = set()


def chitchat_kanban_check(
    agent,
    user_message: str,
    assistant_response: str,
    conversation_history: list,
) -> ChitchatKanbanVerdict:
    """Check whether a chitchat message reveals task-like intent and a
    confirmation prompt should be injected.

    Detection flow:
      - If user says 'yes' while awaiting confirmation → clear state, no new prompt.
      - If message is NOT chitchat → no monitoring (normal kanban flow applies).
      - If chitchat but no prior chitchat exchange → track seen, no prompt yet.
      - If chitchat AND prior chitchat exchange → run intent detection.
        - If intent found AND not yet prompted for this intent → prompt.
        - If intent found BUT already prompted → suppress (debounce).

    Args:
        agent: the AIAgent instance (session state stored as _chitchat_* attrs)
        user_message: the raw user message text
        assistant_response: the assistant's response text
        conversation_history: list of message dicts for this turn

    Returns:
        ChitchatKanbanVerdict with prompt_requested=True when the confirmation
        prompt should be injected.
    """
    _init_chitchat_state(agent)
    verdict = ChitchatKanbanVerdict()

    msg = (user_message or "").strip()

    # ── 'yes' confirmation: clear state, no new prompt ──────────────────────
    if agent._chitchat_awaiting_confirmation and _is_yes_confirmation(msg):
        logger.info("Chitchat kanban: user confirmed 'yes' — clearing pending intent")
        agent._chitchat_awaiting_confirmation = False
        pending = agent._chitchat_pending_intent
        agent._chitchat_pending_intent = None
        # Return a verdict indicating confirmed (caller uses pending_intent to
        # auto-fill the kanban_create call via inline_tool_executors).
        return ChitchatKanbanVerdict(
            prompt_requested=False,
            intent_reason="user_confirmed",
            intent_hash=_intent_hash(pending["user_message"] if pending else "", pending["intent_reason"] if pending else ""),
        )

    # ── Not chitchat: nothing to do ───────────────────────────────────────
    if not is_chitchat(msg):
        # Reset chitchat seen flag when user sends a task message.
        agent._chitchat_seen = False
        agent._chitchat_awaiting_confirmation = False
        agent._chitchat_pending_intent = None
        return verdict

    # ── Chitchat path ───────────────────────────────────────────────────────
    if not agent._chitchat_seen:
        # First chitchat exchange — track but don't prompt yet.
        agent._chitchat_seen = True
        logger.info("Chitchat kanban: first chitchat exchange tracked")
        return verdict

    # At least one prior chitchat exchange — run intent detection.
    detected, reason = detect_tasklike_intent_sync(
        user_message=msg,
        assistant_response=assistant_response or "",
        conversation_history=conversation_history or [],
    )

    if not detected:
        return verdict

    # Intent detected. Check debounce.
    ihash = _intent_hash(msg, reason)
    if ihash in agent._chitchat_prompted_intents:
        logger.info("Chitchat kanban: intent %s already prompted — suppressing (debounce)", ihash)
        return verdict

    # Mark as prompted and store pending intent.
    agent._chitchat_prompted_intents.add(ihash)
    agent._chitchat_awaiting_confirmation = True
    agent._chitchat_pending_intent = {
        "user_message": msg,
        "intent_reason": reason,
        "intent_hash": ihash,
    }
    # Reset so a subsequent user message starts a fresh exchange tracking.
    # The confirmation yes/no response is handled separately.
    agent._chitchat_seen = False

    logger.info("Chitchat kanban: intent detected reason=%s — requesting confirmation", reason)

    return ChitchatKanbanVerdict(
        prompt_requested=True,
        response_with_prompt=None,  # caller must call inject_confirmation()
        intent_reason=reason,
        intent_hash=ihash,
    )


def chitchat_kanban_confirmed_intent(agent) -> Optional[dict]:
    """Return and clear the pending chitchat intent after user confirmation.

    Called by inline_tool_executors.py when the user confirms 'yes' and the
    model calls ``kanban_create``.
    """
    pending = getattr(agent, "_chitchat_pending_intent", None)
    if pending:
        agent._chitchat_pending_intent = None
        agent._chitchat_awaiting_confirmation = False
    return pending


def chitchat_kanban_clear_pending(agent) -> None:
    """Clear all chitchat kanban state (e.g. on session reset)."""
    agent._chitchat_seen = False
    agent._chitchat_awaiting_confirmation = False
    agent._chitchat_pending_intent = None
    agent._chitchat_prompted_intents = set()
