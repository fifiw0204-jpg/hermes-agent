"""Chitchat classifier: distinguishes casual conversation from task-related messages.

Public API
-----------
is_chitchat(message: str) -> bool
    True  → likely chitchat (greeting, small talk, off-topic)
    False → likely task-related (request, assignment, bug report, question)

chitchat_score(message: str) -> tuple[bool, float]
    Returns (is_chitchat, confidence) where confidence is 0.0–1.0.

matched_patterns(message: str) -> list[str]
    Returns the list of pattern names that matched.

Classification layers (applied in order)
----------------------------------------
1. Task blocklist  — phrases that are unambiguously task-related → reject chitchat
2. Greeting regex  — hello, hi, hey, good morning… → chitchat
3. Valediction regex — bye, see you, goodnight… → chitchat
4. Social words frozenset — thank, thanks, please, sorry… → weakly chitchat
5. Smalltalk patterns — what's up, how are you, nice weather… → chitchat
6. Social phrase heuristic — balanced social words vs. task keywords

Each layer appends to matched_patterns so callers can inspect why a score was computed.
"""

from __future__ import annotations

import re
from typing import Final

# ── Layer 1: Task blocklist ───────────────────────────────────────────────────
# Phrases that signal a real task — if any match, the message is NOT chitchat.
_TASK_BLOCKLIST: Final[list[str]] = [
    r"\bfix\b",
    r"\bbug\b",
    r"\berror\b",
    r"\bcrash\b",
    r"\bcrashes?\b",
    r"\bregression\b",
    r"\bdeploy\b",
    r"\bdeploying\b",
    r"\brelease\b",
    r"\breleasing\b",
    r"\bbuild\b",
    r"\bbuilding\b",
    r"\bcompile\b",
    r"\bcompiling\b",
    r"\btest(?:s|ing)?\b",
    r"\brefactor\b",
    r"\brefactoring\b",
    r"\bimplement\b",
    r"\bimplementation\b",
    r"\bfeature\b",
    r"\brequest\b",
    r"\bissue\b",
    r"\bkanban\b",
    r"\btask\b",
    r"\bTODO\b",
    r"\bPR\b",
    r"\bcommit\b",
    r"\bbranch\b",
    r"\bmerge\b",
    r"\bconfig\b",
    r"\bconfiguration\b",
    r"\bsetup\b",
    r"\binstall\b",
    r"\buninstall\b",
    r"\bupdate\b",
    r"\bupdating\b",
    r"\bupgrade\b",
    r"\bdowngrade\b",
    r"\bpatch\b",
    r"\bsecurity\b",
    r"\bvulnerability\b",
    r"\bexploit\b",
    r"\bbreach\b",
    r"\bfail\b",
    r"\bfailing\b",
    r"\boutage\b",
    r"\boutage\b",
    # Programming / engineering task signals
    r"\bfunction\b",
    r"\bclass\b",
    r"\bmodule\b",
    r"\bapi\b",
    r"\bendpoint\b",
    r"\brequest\b",
    r"\bresponse\b",
    r"\bquery\b",
    r"\bdatabase\b",
    r"\bschema\b",
    r"\bmigration\b",
    r"\bscript\b",
    r"\bdaemon\b",
    r"\bservice\b",
    r"\bworker\b",
    r"\bqueue\b",
    r"\bcache\b",
    r"\bperformance\b",
    r"\blatency\b",
    r"\bthroughput\b",
    r"\bscaling\b",
    r"\breplica\b",
    r"\bfailover\b",
    r"\bbackup\b",
    r"\brestore\b",
    # Explicit task assignment patterns
    r"\bcreate\b.*\btask\b",
    r"\bregister\b.*\btask\b",
    r"\badd\b.*\bkanban\b",
    r"\bschedule\b",
    r"\bdeadline\b",
    r"\basap\b",
    r"\burgent\b",
    r"\bpriority\b",
]

_TASK_BLOCKLIST_RE: Final[re.Pattern] = re.compile(
    "|".join(_TASK_BLOCKLIST), re.IGNORECASE
)

# ── Layer 2: Greeting patterns ───────────────────────────────────────────────
_GREETING_PATTERNS: Final[list[str]] = [
    r"^\s*hi\b",
    r"^\s*hey\b",
    r"^\s*hello\b",
    r"^\s*hi there\b",
    r"^\s*hey there\b",
    r"^\s*greetings\b",
    r"^\s*good morning\b",
    r"^\s*good afternoon\b",
    r"^\s*good evening\b",
    r"^\s*yo\b",
    r"^\s*sup\b",
    r"^\s*wassup\b",
    r"^\s*howdy\b",
    r"^\s*ola\b",
    r"^\s*bonjour\b",
    r"^\s*ciao\b",
    r"^\s*hola\b",
    r"^\s*namaste\b",
    r"^\s*ni hao\b",
    r"^\s*anneyong\b",
    # Chinese casual greetings
    r"^\s*嗨\b",
    r"^\s*哈囉\b",
    r"^\s*你好\b",
    r"^\s*早安\b",
    r"^\s*晚安\b",
]

_GREETING_RE: Final[re.Pattern] = re.compile(
    "|".join(_GREETING_PATTERNS), re.IGNORECASE
)

# ── Layer 3: Valediction patterns ────────────────────────────────────────────
_VALEDICTION_PATTERNS: Final[list[str]] = [
    r"\bgoodbye\b",
    r"\bbyebye\b",
    r"\bbye\b",
    r"\bsee you\b",
    r"\bsee ya\b",
    r"\blater\b",
    r"\bttyl\b",
    r"\bgoodnight\b",
    r"\bsleep well\b",
    r"\btake care\b",
    r"\bhave a good\b",
    r"\bhave a nice\b",
    r"\bthat's all\b",
    r"\bnothing more\b",
    r"\bthat's it\b",
    r"\bgoing now\b",
    r"\bgotta go\b",
    r"\bbrb\b",
]

_VALEDICTION_RE: Final[re.Pattern] = re.compile(
    "|".join(_VALEDICTION_PATTERNS), re.IGNORECASE
)

# ── Layer 4: Social words frozenset ─────────────────────────────────────────
# Presence of these words weakly nudges toward chitchat. Absence does not push
# toward task.
_SOCIAL_WORDS: Final[frozenset[str]] = frozenset({
    "thanks", "thank", "thankyou",
    "please", "pls",
    "sorry", "apologies", "apology",
    "great", "awesome", "cool", "nice",
    "wonderful", "amazing", "lovely",
    "fantastic", "excellent",
    "good", "fine", "okay", "ok",
    "happy", "glad", "pleased",
    "congratulations", "congrats",
    "cheers", "appreciate", "appreciated",
    "welcome", "welcoming",
    "regards", "kindly",
    "respectfully",
    "indeed", "certainly", "absolutely",
})

# ── Layer 5: Smalltalk patterns ──────────────────────────────────────────────
_SMALLTALK_PATTERNS: Final[list[str]] = [
    r"how are you",
    r"how('s| is) (it|things|life|everything|work|your day)",
    r"what('s| is) up",
    r"wassup",
    r"what('s| is) new",
    r"how('s| is) your (day|weekend|evening|morning|week)",
    r"nice weather",
    r"beautiful day",
    r"(have|had) a good (day|weekend|night|evening)",
    r"(have|had) a (nice|great|wonderful) (day|weekend|evening)",
    r"enjoy your (day|evening|night|weekend)",
    r"hope you('re| are) (doing )?well",
    r"sounds great",
    r"sounds good",
    r"that('s| is) (great|good|nice|cool|awesome)",
    r"i (think|guess|suppose|believe|feel) (that |it )?",
    r"i('m| am) (just |really |quite )?",
    r"just (wondering|checking|asking|wanted to)",
    r"(by the way|btw)",
    r"(oh |wow |hey )?never mind",
    r"never mind",
    r"(long time|no news)",
    r"long time no see",
    r"it('s| is) been (a )?",
    r"what do you think (about|of)",
    r"what('s| is) your opinion",
    r"do you (like|enjoy|prefer)",
    r"(just|merely) (curious|interested)",
    r"(no|not) (a problem|worries|trouble)",
    r"no worries",
    r"all (good|right|fine|okay)",
    r"no (worries|problem|trouble)",
    r"you('re| are) welcome",
]

_SMALLTALK_RE: Final[re.Pattern] = re.compile(
    "|".join(_SMALLTALK_PATTERNS), re.IGNORECASE
)

# ── Layer 6: Social phrase heuristic ────────────────────────────────────────
# Count social vs task keywords. A message with predominantly social words is
# chitchat; one with task words is not.
_TASK_KEYWORDS: Final[frozenset[str]] = frozenset({
    "fix", "bug", "error", "issue", "problem", "crash", "failure", "fail",
    "implement", "feature", "design", "architect", "refactor", "optimize",
    "deploy", "release", "build", "compile", "test", "debug", "profile",
    "configure", "setup", "install", "upgrade", "migrate", "migrate",
    "api", "endpoint", "function", "class", "method", "module", "package",
    "database", "schema", "query", "cache", "queue", "worker", "service",
    "docker", "kubernetes", "container", "server", "client", "protocol",
    "security", "auth", "permission", "access", "token", "credential",
    "performance", "latency", "throughput", "benchmark", "monitoring",
    "log", "logging", "tracing", "alert", "alerting", "incident",
    "task", "kanban", "ticket", "jira", "linear", "asana", "todo",
    "github", "gitlab", "bitbucket", "pr", "pull request", "commit",
    "branch", "merge", "diff", "review", "approve",
    "script", "automation", "pipeline", "ci", "cd",
    "config", "env", "variable", "secret", "key",
    "file", "directory", "path", "folder", "structure",
})

_SOCIAL_PHRASE_INDICATORS: Final[frozenset[str]] = frozenset({
    "weather", "weekend", "holiday", "vacation", "trip", "travel",
    "lunch", "dinner", "breakfast", "coffee", "tea", "beer", "wine",
    "movie", "film", "series", "show", "book", "music", "song",
    "game", "gaming", "sport", "exercise", "workout", "run", "run",
    "family", "friend", "friend", "party", "celebration",
    "birthday", "anniversary", "congrats", "cheers",
    "mood", "feeling", "emotion", "happy", "sad", "tired", "excited",
})


def _tokenise(text: str) -> list[str]:
    """Lower-case word tokens, stripped of punctuation."""
    return re.findall(r"\b\w+\b", text.lower())


def matched_patterns(message: str) -> list[str]:
    """Return the list of pattern names that matched for `message`."""
    patterns: list[str] = []
    text = message.strip()

    # Layer 1: task blocklist
    if _TASK_BLOCKLIST_RE.search(text):
        patterns.append("task_blocklist")

    # Layer 2: greeting
    if _GREETING_RE.match(text):
        patterns.append("greeting")

    # Layer 3: valediction
    if _VALEDICTION_RE.search(text):
        patterns.append("valediction")

    # Layer 4: social words
    tokens = _tokenise(text)
    social_hits = [t for t in tokens if t in _SOCIAL_WORDS]
    if social_hits:
        patterns.append(f"social_words:{social_hits}")

    # Layer 5: smalltalk
    if _SMALLTALK_RE.search(text):
        patterns.append("smalltalk")

    # Layer 6: social phrase indicators
    phrase_hits = [t for t in tokens if t in _SOCIAL_PHRASE_INDICATORS]
    if phrase_hits:
        patterns.append(f"social_phrases:{phrase_hits}")

    return patterns


def chitchat_score(message: str) -> tuple[bool, float]:
    """Return (is_chitchat, confidence) for `message`.

    Confidence is 0.0–1.0 and reflects how many layers fired.
    """
    text = message.strip()
    if not text:
        return False, 0.0

    score = 0.0
    max_score = 6.0  # six layers

    # Layer 1: task blocklist → immediate non-chitchat (high confidence)
    if _TASK_BLOCKLIST_RE.search(text):
        return False, 0.95

    # Layer 2: greeting → chitchat
    if _GREETING_RE.match(text):
        score += 1.0

    # Layer 3: valediction → chitchat
    if _VALEDICTION_RE.search(text):
        score += 1.0

    # Layer 4: social words — each hit scores 0.5, capped at 1.0
    tokens = _tokenise(text)
    social_hits = [t for t in tokens if t in _SOCIAL_WORDS]
    if social_hits:
        score += min(1.0, len(social_hits) * 0.5)

    # Layer 5: smalltalk patterns
    if _SMALLTALK_RE.search(text):
        score += 1.5

    # Layer 6: social phrase indicators — each hit scores 0.5, capped at 1.0
    phrase_hits = [t for t in tokens if t in _SOCIAL_PHRASE_INDICATORS]
    if phrase_hits:
        score += min(1.0, len(phrase_hits) * 0.5)

    # Normalise to 0.0–1.0
    confidence = min(1.0, score / max_score)

    # Threshold: > 0.4 → chitchat
    is_chitchat = score > 0.4

    return is_chitchat, round(confidence, 2)


def is_chitchat(message: str) -> bool:
    """Return True if `message` is likely chitchat, False if task-related."""
    return chitchat_score(message)[0]


def non_chitchat_register(message: str) -> bool:
    """Return True when ``message`` is a task-worthy message that should be
    registered in Hermes kanban WITHOUT requiring the chitchat-after-cascade
    confirmation prompt.

    This is a convenience alias for the most common non-chitchat decision:
    ``not is_chitchat(message)``.  Callers who need the confidence score
    should call ``chitchat_score()`` directly.
    """
    return not is_chitchat(message)
