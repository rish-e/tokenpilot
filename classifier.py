"""Lightweight task classifier using regex + keyword heuristics.

No LLM calls — must execute in <10ms for hook latency requirements.
v2: Added negation detection, quoted-code filtering, adjacency scoring, debug mode.
"""

import re

# Negation prefixes that cancel the next keyword match
NEGATION_PATTERN = re.compile(
    r"\b(don'?t|do\s+not|stop|no|without|never|skip|avoid|shouldn'?t|won'?t)\s+",
    re.IGNORECASE,
)

# Patterns ordered from most to least specific
TRIVIAL_PATTERNS = [
    r"\b(fix|correct)\s+(typo|spelling|whitespace|indent)",
    r"\b(rename|move)\s+.+\s+(to|->)",
    r"\b(add|remove|delete)\s+(comment|import|log)\b",
    r"\b(update|change|set)\s+(version|name|title|label|placeholder)",
    r"\b(format|lint|prettify)\b",
    r"\bbump\s+(version|dep)",
]

RESEARCH_PATTERNS = [
    r"\b(explain|understand|how\s+does|what\s+is|describe|show\s+me)\b",
    r"\b(find|search|look\s+for|where\s+is|locate)\b",
    r"\b(list|show|display|print)\s+(all|every|the)\b",
    r"\b(compare|diff|difference)\b",
    r"\b(check|verify|validate|inspect)\b",
]

COMPLEX_PATTERNS = [
    r"\b(refactor|restructure|redesign|rearchitect|migrate)\b",
    r"\b(implement|build|create)\s+.{20,}",
    r"\b(multi.?file|across\s+(files|modules|components|services|microservices|the\s+\w+))\b",
    r"\b(security|auth\w*|encrypt|permission|access\s+control)\b",
    r"\b(database|schema|migration|model)\s+(design|change|update)",
    r"\b(CI|CD|pipeline|deploy|infrastructure)\b",
    r"\b(performance|optimiz\w+|cache|caching|concurrent)\b",
    r"\b(test\s+suite|integration\s+test|e2e)\b",
]

# Adjacency boosters — pairs of keywords that together signal complexity
COMPLEXITY_PAIRS = [
    (r"\b(add|implement|build)\b", r"\b\d+\s+(route|endpoint|file|page|component)s?\b"),
    (r"\b(add|implement)\b", r"\b(auth\w*|security|encrypt)\b"),
    (r"\b(across|every|all)\b", r"\b(file|module|service|route|endpoint)s?\b"),
]

EFFORT_MAP = {
    "trivial": "low",
    "research": "medium",
    "standard": "medium",
    "complex": "high",
}

MODEL_HINT_MAP = {
    "trivial": "haiku",
    "research": "sonnet",
    "standard": "sonnet",
    "complex": "opus",
}


def _strip_quoted_code(text: str) -> str:
    """Remove backtick-wrapped content before classification."""
    # Remove triple backtick blocks
    text = re.sub(r"```[\s\S]*?```", " ", text)
    # Remove inline backticks
    text = re.sub(r"`[^`]+`", " ", text)
    return text


def _check_negated(text: str, pattern: str) -> bool:
    """Check if a pattern match is preceded by a negation word."""
    match = re.search(pattern, text)
    if not match:
        return False
    # Look for negation in the 30 chars before the match
    start = max(0, match.start() - 30)
    prefix = text[start:match.start()]
    return bool(NEGATION_PATTERN.search(prefix))


def _count_matches(text: str, patterns: list[str]) -> int:
    """Count pattern matches, excluding negated ones."""
    count = 0
    for p in patterns:
        if re.search(p, text) and not _check_negated(text, p):
            count += 1
    return count


def _check_adjacency(text: str) -> int:
    """Check for keyword pairs that signal complexity when adjacent."""
    score = 0
    for p1, p2 in COMPLEXITY_PAIRS:
        if re.search(p1, text) and re.search(p2, text):
            score += 1
    return score


def classify_task(prompt: str) -> dict:
    """Classify a user prompt into a task category.

    Returns dict with:
        category: trivial | research | standard | complex
        effort: low | medium | high
        model_hint: haiku | sonnet | opus
        confidence: float 0-1
    """
    raw_text = prompt.lower().strip()
    text = _strip_quoted_code(raw_text)

    # Very short prompts — low confidence
    if len(text) < 10:
        return _result("trivial", 0.3)

    if len(text) < 20:
        for pattern in TRIVIAL_PATTERNS:
            if re.search(pattern, text) and not _check_negated(text, pattern):
                return _result("trivial", 0.7)
        return _result("trivial", 0.4)

    # Check adjacency pairs first (strong signal)
    adjacency_score = _check_adjacency(text)

    # Check trivial patterns
    trivial_matches = _count_matches(text, TRIVIAL_PATTERNS)
    if trivial_matches >= 2:
        return _result("trivial", 0.9)
    if trivial_matches == 1 and len(text) < 60 and adjacency_score == 0:
        return _result("trivial", 0.7)

    # Check complex patterns
    complex_matches = _count_matches(text, COMPLEX_PATTERNS)
    total_complex = complex_matches + adjacency_score

    if total_complex >= 2:
        return _result("complex", 0.8)
    if total_complex == 1 and len(text) > 40:
        return _result("complex", 0.6)

    # Check research patterns
    research_matches = _count_matches(text, RESEARCH_PATTERNS)
    # "explain AND implement" = complex, not research
    if research_matches >= 1 and complex_matches >= 1:
        return _result("complex", 0.7)
    if research_matches >= 2:
        return _result("research", 0.8)
    if research_matches == 1:
        return _result("research", 0.6)

    # Default: standard
    return _result("standard", 0.5)


def classify_debug(prompt: str) -> dict:
    """Classify with full debug info showing which patterns matched."""
    raw_text = prompt.lower().strip()
    text = _strip_quoted_code(raw_text)

    trivial_matched = [p for p in TRIVIAL_PATTERNS if re.search(p, text)]
    complex_matched = [p for p in COMPLEX_PATTERNS if re.search(p, text)]
    research_matched = [p for p in RESEARCH_PATTERNS if re.search(p, text)]
    adjacency_score = _check_adjacency(text)

    negated = []
    for p in trivial_matched + complex_matched + research_matched:
        if _check_negated(text, p):
            negated.append(p)

    result = classify_task(prompt)
    result["debug"] = {
        "text_length": len(text),
        "stripped_text": text[:100],
        "trivial_patterns": trivial_matched,
        "complex_patterns": complex_matched,
        "research_patterns": research_matched,
        "negated_patterns": negated,
        "adjacency_score": adjacency_score,
    }
    return result


def _result(category: str, confidence: float) -> dict:
    return {
        "category": category,
        "effort": EFFORT_MAP[category],
        "model_hint": MODEL_HINT_MAP[category],
        "confidence": round(confidence, 2),
    }
