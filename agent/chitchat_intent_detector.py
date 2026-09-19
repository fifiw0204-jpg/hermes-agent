"""Task-like intent detector for chitchat-aware kanban flow.

After at least one chitchat exchange, monitors the ongoing conversation for
task-like intent. Used when ``is_chitchat(message) == True`` to decide whether
to prompt the user with '是否要將這個登記為 task？'.

Detection logic (documented for maintainability):
  - Deterministic keyword + pattern matching against conversation context
  - Looks for: work verbs, problem statements, request patterns, pain/complaint
  - Guards: social-only messages are excluded even if they contain keywords
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger("agent.chitchat_intent_detector")

# ── Deterministic patterns ────────────────────────────────────────────────────
# Intentionally conservative (high precision, lower recall) to avoid
# false positives that would spam the confirmation prompt.

# Task-like intent: work verbs, problem statements, explicit requests, pain/complaint.
# CJK characters have no word boundaries so patterns are bare prefixes.
_TASK_INTENT_KEYWORD_PATTERNS = [
    # Explicit work / action verbs (English + Chinese characters)
    r"(?i)\b(write|build|fix|create|implement|debug|check|find|look\s+at|analyze|audit|refactor|test|run|do|delete|remove|update)\b",
    r"(?i)(需要|想要|帮我|幫我|create|implement|delete|remove|update|写|創|建|建造|开发|開發|修复|修復|檢查|檢查|刪除|更新)",
    # Explicit problem statements
    r"(?i)\b(bug|issue|problem|broken|crash|error|fail|failing|not\s+working|doesn't\s+work|doesn't\s+exist)\b",
    r"(?i)(bug|错误|錯誤|问题|問題|崩溃|崩潰|故障|失败|失敗)",
    # Explicit task/todo framing
    r"(?i)\b(todo|to.?do|task|ticket|kanban)\b",
    r"(?i)(登记|登記|工作|任務|todo)",
    # Explicit request patterns
    r"(?i)\b(can\s+you|please|how\s+do\s+i|how\s+can\s+i|what'?s?\s+the|explain|show\s+me|give\s+me)\b",
    r"(?i)(能不能|可不可以|帮我|幫我|请|請)",
    # Pain-point / complaint language
    r"(?i)\b(hate|annoying|frustrat|tired\s+of|wish\s+it|could\s+you|should\s+add|should\s+be|improve|optimize)\b",
    r"(?i)(自动化|自動|自动化|讨厌|討厭|烦|煩|希望|希望|应该|應該)\b",
    # Goal-oriented language
    r"(?i)\b(goal|objective|plan|finish|complete|accomplish)\b",
    r"(?i)(打算|计划|计划|目标|目標|想要完成|完成|實現)\b",
]
_TASK_INTENT_RE = re.compile("|".join(_TASK_INTENT_KEYWORD_PATTERNS), re.IGNORECASE)

# Patterns that, if matched, should NOT by themselves trigger intent
# (pure social/reaction words with no task content).
_SOFT_SOCIAL_PATTERNS = [
    r"(?i)^\s*(hi|hey|hello|bye|goodbye|thanks?|thank\s+you|ok|okay|sure|yeah|yes|yep|nope|no|cool|nice|great|good|fine)\s*$",
    r"(?i)^\s*(lol|haha|wow|gosh|gee|yikes|whoa|oh|ah|eh|um|uh|hmm|hm)\s*$",
    r"(?i)^\s*(what'?s\s+up|wassup|howdy|greetings|nice\s+to\s+meet\s+you)\s*$",
    r"(?i)^\s*(早安|晚安|你好|嗨|哈囉|掰掰)\s*$",
]
_SOFT_SOCIAL_RE = [re.compile(p, re.IGNORECASE) for p in _SOFT_SOCIAL_PATTERNS]

# Assistant commitment language: when the assistant has committed to doing work.
_ASSISTANT_COMMITMENT_RE = re.compile(
    r"(?i)\b(i'll|i\s+will|i\s+can|i\s+should|let\s+me|i'?ll?\s+go|going\s+to|"
    r"will\s+do|can\s+do|will\s+handle|can\s+handle|"
    r"我會|我來|我来|我幫你|我帮你|我來幫|我來做)\s+"
    r"(write|build|fix|create|check|find|analyze|look\s+at|implement|run|do|幫|写|做|處理)\b",
    re.IGNORECASE,
)


def _is_social_only(text: str) -> bool:
    """Return True if text is purely social/reaction with no meaningful task signal.

    Guards against false positives from messages that contain a task keyword
    in a purely social context (e.g. 'great, fix that bug for me' — the 'fix'
    is a request, not social).
    """
    if not text or not isinstance(text, str):
        return True
    stripped = text.strip()
    if not stripped:
        return True
    if len(stripped) <= 3:
        return True
    for pattern_re in _SOFT_SOCIAL_RE:
        if pattern_re.match(stripped):
            return True
    return False


def _extract_text_content(value: Optional[str | list]) -> str:
    """Flatten a message content field (str or list of content blocks) to plain text."""
    if not value:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for block in value:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "reflection":
                    parts.append(block.get("summary", ""))
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts)
    return str(value)


def _detect_tasklike_intent_deterministic(
    user_message: str,
    assistant_response: str,
    conversation_history: list[dict],
) -> tuple[bool, str]:
    """Deterministic intent detection via keyword + pattern matching.

    Returns (intent_detected: bool, reason: str).

    Detection rules:
      1. Pure social-only messages never trigger intent.
      2. User message with task keywords → intent.
      3. Assistant response with commitment language → intent (assistant promised work).
      4. History scan: if any assistant message in history has commitment language → intent.
    """
    user_text = _extract_text_content(user_message) if isinstance(user_message, (str, list)) else str(user_message or "")
    assistant_text = _extract_text_content(assistant_response) if isinstance(assistant_response, (str, list)) else str(assistant_response or "")

    # Rule 1: social-only messages never trigger
    if _is_social_only(user_text):
        return False, ""

    # Rule 2: user message has task keywords
    if _TASK_INTENT_RE.search(user_text):
        return True, "keyword_match:user_message"

    # Rule 3: assistant response has commitment language
    if _ASSISTANT_COMMITMENT_RE.search(assistant_text):
        return True, "keyword_match:assistant_commitment"

    # Rule 4: scan conversation history for assistant commitment language
    if conversation_history:
        for msg in conversation_history:
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                content = _extract_text_content(msg.get("content"))
                if _ASSISTANT_COMMITMENT_RE.search(content):
                    return True, "keyword_match:history_assistant_commitment"

    return False, ""


def detect_tasklike_intent_sync(
    user_message: str,
    assistant_response: str,
    conversation_history: list[dict],
) -> tuple[bool, str]:
    """Primary intent detection entry point (synchronous, no external dependencies).

    Returns (intent_detected: bool, reason: str).
    """
    return _detect_tasklike_intent_deterministic(user_message, assistant_response, conversation_history)
