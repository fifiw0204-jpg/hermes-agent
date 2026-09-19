"""Unit tests for the chitchat-aware kanban flow (t_0fa1633b)."""

import pytest
from agent.chitchat_classifier import is_chitchat, non_chitchat_register
from agent.chitchat_intent_detector import (
    detect_tasklike_intent_sync,
    _detect_tasklike_intent_deterministic,
    _is_social_only,
    _extract_text_content,
)
from agent.chitchat_kanban_flow import (
    chitchat_kanban_check,
    chitchat_kanban_confirmed_intent,
    chitchat_kanban_clear_pending,
    CHITCHAT_CONFIRMATION_PROMPT,
    _is_yes_confirmation,
    _intent_hash,
    _init_chitchat_state,
)


# ── is_chitchat ─────────────────────────────────────────────────────────────────

class TestIsChitchat:
    def test_greeting_true(self):
        assert is_chitchat("hi") is True
        assert is_chitchat("hello") is True
        assert is_chitchat("嗨") is True
        assert is_chitchat("good morning") is True

    def test_task_false(self):
        assert is_chitchat("帮我写个脚本") is False
        assert is_chitchat("fix the bug") is False
        assert is_chitchat("create a PR") is False
        assert is_chitchat("what is the capital of France?") is False

    def test_valediction_true(self):
        assert is_chitchat("bye") is True
        assert is_chitchat("goodbye") is True
        assert is_chitchat("see you") is True

    def test_social_ack_true(self):
        assert is_chitchat("ok") is True
        assert is_chitchat("cool") is True
        assert is_chitchat("great") is True


# ── non_chitchat_register ────────────────────────────────────────────────────────

class TestNonChitchatRegister:
    def test_greeting_false(self):
        """Greeting is chitchat → not registered directly."""
        assert non_chitchat_register("hi") is False
        assert non_chitchat_register("hello") is False
        assert non_chitchat_register("你好") is False

    def test_task_true(self):
        """Task-worthy message → registered directly."""
        assert non_chitchat_register("帮我写个脚本") is True
        assert non_chitchat_register("fix the bug") is True
        assert non_chitchat_register("帮我调查这个问题") is True

    def test_valediction_false(self):
        """Valediction is chitchat → not registered directly."""
        assert non_chitchat_register("bye") is False
        assert non_chitchat_register("goodbye") is False

    def test_is_chitchat_alias(self):
        """non_chitchat_register is exactly not is_chitchat."""
        for msg in ("hi", "hello", "bye", "ok", "cool"):
            assert non_chitchat_register(msg) is (not is_chitchat(msg))
        for msg in ("fix the bug", "帮我写脚本", "create a task"):
            assert non_chitchat_register(msg) is (not is_chitchat(msg))


# ── _is_social_only ─────────────────────────────────────────────────────────────

class TestIsSocialOnly:
    def test_pure_greeting(self):
        assert _is_social_only("hi") is True
        assert _is_social_only("hello") is True
        assert _is_social_only("ok") is True

    def test_task_phrase_not_social(self):
        assert _is_social_only("fix the bug") is False
        assert _is_social_only("帮我写脚本") is False

    def test_empty(self):
        assert _is_social_only("") is True
        assert _is_social_only(None) is True


# ── detect_tasklike_intent_sync ────────────────────────────────────────────────

class TestDetectTasklikeIntent:
    def test_chitchat_then_task_intent(self):
        """Chitchat followed by task intent should be detected."""
        history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "Hello! How are you?"},
        ]
        detected, reason = detect_tasklike_intent_sync(
            "對了我有個 bug", "哪個？", history
        )
        assert detected is True, f"Expected True, got {detected}, reason={reason}"

    def test_pure_chitchat_no_intent(self):
        """Chitchat without task keywords should not trigger intent."""
        history = [{"role": "user", "content": "hello"}]
        detected, reason = detect_tasklike_intent_sync(
            "hi how are you", "I am fine!", history
        )
        assert detected is False, f"Expected False, got {detected}"

    def test_assistant_commitment_alone_not_enough(self):
        """Pure social user message + assistant commitment in history should NOT trigger.

        The intent signal must come from the user (or current assistant response),
        not from history alone when the user says something purely social.
        """
        history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "I'll help you fix that bug right away."},
        ]
        detected, reason = detect_tasklike_intent_sync(
            "great", "Glad you like it!", history
        )
        # User said "great" — purely social. The assistant's commitment in history
        # is not enough to trigger task creation when the user is not expressing intent.
        assert detected is False, f"Expected False for purely social user message, got {detected}"

    def test_assistant_commitment_plus_user_intent(self):
        """User expressing need + assistant has commitment in history → intent detected."""
        history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "Sure, I'll fix the bug."},
        ]
        detected, reason = detect_tasklike_intent_sync(
            "對了那個 bug", "哪個？", history
        )
        assert detected is True, f"Expected True, got {detected}"

    def test_user_task_keyword_direct(self):
        """Direct task request should trigger intent."""
        history = []
        detected, reason = detect_tasklike_intent_sync(
            "帮我写一个脚本", "好的，写什么脚本？", history
        )
        assert detected is True, f"Expected True, got {detected}"

    def test_social_only_user_message(self):
        """Pure social user message should not trigger intent even with history."""
        history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        detected, reason = detect_tasklike_intent_sync(
            "cool", "Glad you like it!", history
        )
        assert detected is False, f"Expected False, got {detected}"


# ── _is_yes_confirmation ────────────────────────────────────────────────────────

class TestIsYesConfirmation:
    def test_yes_variants(self):
        assert _is_yes_confirmation("yes") is True
        assert _is_yes_confirmation("yep") is True
        assert _is_yes_confirmation("yeah") is True
        assert _is_yes_confirmation("ok") is True
        assert _is_yes_confirmation("okay") is True
        assert _is_yes_confirmation("sure") is True
        assert _is_yes_confirmation("好") is True
        assert _is_yes_confirmation("是") is True
        assert _is_yes_confirmation("對") is True

    def test_no_variants(self):
        assert _is_yes_confirmation("no") is False
        assert _is_yes_confirmation("nope") is False
        assert _is_yes_confirmation("not") is False
        assert _is_yes_confirmation("算了") is False


# ── _intent_hash ────────────────────────────────────────────────────────────────

class TestIntentHash:
    def test_same_inputs_same_hash(self):
        h1 = _intent_hash("fix the bug", "keyword_match:user_message")
        h2 = _intent_hash("fix the bug", "keyword_match:user_message")
        assert h1 == h2

    def test_different_inputs_different_hash(self):
        h1 = _intent_hash("fix the bug", "keyword_match:user_message")
        h2 = _intent_hash("build a script", "keyword_match:user_message")
        assert h1 != h2


# ── _init_chitchat_state ───────────────────────────────────────────────────────

class FakeAgent:
    pass


class TestInitChitchatState:
    def test_initializes_all_attributes(self):
        agent = FakeAgent()
        _init_chitchat_state(agent)
        assert hasattr(agent, "_chitchat_seen")
        assert hasattr(agent, "_chitchat_awaiting_confirmation")
        assert hasattr(agent, "_chitchat_pending_intent")
        assert hasattr(agent, "_chitchat_prompted_intents")

    def test_idempotent(self):
        agent = FakeAgent()
        _init_chitchat_state(agent)
        agent._chitchat_seen = True
        _init_chitchat_state(agent)
        assert agent._chitchat_seen is True


# ── chitchat_kanban_check ───────────────────────────────────────────────────────

class TestChitchatKanbanCheck:
    def test_first_chitchat_no_prompt(self):
        """First chitchat exchange should not prompt (need >= 1 prior first)."""
        agent = FakeAgent()
        _init_chitchat_state(agent)
        verdict = chitchat_kanban_check(
            agent=agent,
            user_message="hi",
            assistant_response="Hello!",
            conversation_history=[],
        )
        assert verdict.prompt_requested is False
        assert agent._chitchat_seen is True

    def test_second_chitchat_intent_from_history(self):
        """Intent from conversation HISTORY should trigger prompt on second chitchat.

        The user message here is chitchat (passes is_chitchat()).
        The task intent comes from the ASSISTANT's commitment in history.
        After >=1 prior chitchat exchange, this should trigger the prompt.
        """
        agent = FakeAgent()
        _init_chitchat_state(agent)
        agent._chitchat_seen = True  # simulate prior chitchat exchange

        history = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "Sure, I'll write a script to automate this for you.",
            },
        ]
        # User's message is pure social acknowledgment; intent is in history assistant
        verdict = chitchat_kanban_check(
            agent=agent,
            user_message="great, that would be helpful",
            assistant_response="What data does it need to process?",
            conversation_history=history,
        )
        # History assistant commitment → intent detected → prompt requested
        assert verdict.prompt_requested is True, f"Expected True, got {verdict}"
        assert verdict.intent_reason == "keyword_match:history_assistant_commitment"
        assert agent._chitchat_awaiting_confirmation is True

    def test_non_chitchat_resets_state(self):
        """Non-chitchat message should reset chitchat state."""
        agent = FakeAgent()
        _init_chitchat_state(agent)
        agent._chitchat_seen = True
        agent._chitchat_awaiting_confirmation = True
        agent._chitchat_pending_intent = {"user_message": "test"}
        verdict = chitchat_kanban_check(
            agent=agent,
            user_message="帮我写个脚本",
            assistant_response="好的",
            conversation_history=[],
        )
        assert verdict.prompt_requested is False
        assert agent._chitchat_seen is False
        assert agent._chitchat_awaiting_confirmation is False

    def test_non_chitchat_direct_register_true(self):
        """Non-chitchat (task-worthy) message → direct_register=True."""
        agent = FakeAgent()
        _init_chitchat_state(agent)
        verdict = chitchat_kanban_check(
            agent=agent,
            user_message="帮我写个脚本",
            assistant_response="好的，写什么脚本？",
            conversation_history=[],
        )
        assert verdict.prompt_requested is False
        assert verdict.direct_register is True

    def test_non_chitchat_kanban_flow_clears_all_chitchat_state(self):
        """Non-chitchat resets all chitchat state AND sets direct_register."""
        agent = FakeAgent()
        _init_chitchat_state(agent)
        agent._chitchat_seen = True
        agent._chitchat_awaiting_confirmation = True
        agent._chitchat_pending_intent = {"user_message": "之前的 pending"}
        verdict = chitchat_kanban_check(
            agent=agent,
            user_message="fix the bug",
            assistant_response="Which one?",
            conversation_history=[],
        )
        assert verdict.direct_register is True
        assert verdict.prompt_requested is False
        assert agent._chitchat_seen is False
        assert agent._chitchat_awaiting_confirmation is False
        assert agent._chitchat_pending_intent is None

    def test_yes_confirmation_clears_pending(self):
        """User saying 'yes' should clear pending intent."""
        agent = FakeAgent()
        _init_chitchat_state(agent)
        agent._chitchat_awaiting_confirmation = True
        agent._chitchat_pending_intent = {
            "user_message": "fix the bug",
            "intent_reason": "keyword_match:user_message",
            "intent_hash": "abc123",
        }
        verdict = chitchat_kanban_check(
            agent=agent,
            user_message="yes",
            assistant_response="好的，我來建立 task。",
            conversation_history=[],
        )
        assert verdict.prompt_requested is False
        assert agent._chitchat_awaiting_confirmation is False
        assert agent._chitchat_pending_intent is None

    def test_debounce_same_intent_suppressed(self):
        """Same intent should not prompt twice (debounce).

        The user's chitchat message alone has no task keywords (so is_chitchat=True).
        The intent signal comes from the assistant's commitment in the CURRENT response.
        After >=1 prior chitchat exchange, intent is detected and prompted.
        On the second call (same user message → same intent), debounce suppresses.
        """
        agent = FakeAgent()
        _init_chitchat_state(agent)

        # First call: second chitchat + assistant commitment → intent detected → prompted
        agent._chitchat_seen = True
        verdict1 = chitchat_kanban_check(
            agent=agent,
            # Pure social chitchat message (no task keywords)
            user_message="great, thanks for the help",
            # Assistant response has commitment language → triggers intent
            assistant_response="Sure, I'll write a script to automate this for you.",
            conversation_history=[],
        )
        assert verdict1.prompt_requested is True, f"Expected True, got {verdict1}"
        assert agent._chitchat_seen is False  # reset after detection
        h = _intent_hash("great, thanks for the help", verdict1.intent_reason)
        assert h in agent._chitchat_prompted_intents

        # Second call: same chitchat + same intent → debounced (suppressed)
        agent._chitchat_seen = True
        verdict2 = chitchat_kanban_check(
            agent=agent,
            user_message="great, thanks for the help",
            assistant_response="Sure, I'll write a script to automate this for you.",
            conversation_history=[],
        )
        assert verdict2.prompt_requested is False, "Same intent should be debounced"

    def test_confirmation_prompt_injected(self):
        """Verdict.inject_confirmation should append the confirmation prompt."""
        agent = FakeAgent()
        _init_chitchat_state(agent)
        agent._chitchat_seen = True
        verdict = chitchat_kanban_check(
            agent=agent,
            user_message="fix the bug",
            assistant_response="Which one?",
            conversation_history=[],
        )
        base = "Which one?"
        result = verdict.inject_confirmation(base)
        assert CHITCHAT_CONFIRMATION_PROMPT in result
        assert base in result


# ── chitchat_kanban_clear_pending ──────────────────────────────────────────────

class TestChitchatKanbanClearPending:
    def test_clears_all_state(self):
        agent = FakeAgent()
        _init_chitchat_state(agent)
        agent._chitchat_seen = True
        agent._chitchat_awaiting_confirmation = True
        agent._chitchat_pending_intent = {"user_message": "test"}
        agent._chitchat_prompted_intents = {"hash1", "hash2"}
        chitchat_kanban_clear_pending(agent)
        assert agent._chitchat_seen is False
        assert agent._chitchat_awaiting_confirmation is False
        assert agent._chitchat_pending_intent is None
        assert agent._chitchat_prompted_intents == set()
