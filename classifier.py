"""Lightweight task classifier using regex + keyword heuristics.

No LLM calls — must execute in <10ms for hook latency requirements.
"""

import re

# Patterns ordered from most to least specific
TRIVIAL_PATTERNS = [
    r"\b(fix|correct)\s+(typo|spelling|whitespace|indent)",
    r"\b(rename|move)\s+\w+\s+(to|->)",
    r"\b(add|remove|delete)\s+(comment|import|log)",
    r"\b(update|change|set)\s+(version|name|title|label|placeholder)",
    r"\b(format|lint|prettify)\b",
    r"\bbump\s+(version|dep)",
]

RESEARCH_PATTERNS = [
    r"\b(explain|understand|how\s+does|what\s+is|describe|show\s+me|read)\b",
    r"\b(find|search|look\s+for|where\s+is|locate)\b",
    r"\b(list|show|display|print)\s+(all|every|the)\b",
    r"\b(compare|diff|difference)\b",
    r"\b(check|verify|validate|inspect)\b",
]

COMPLEX_PATTERNS = [
    r"\b(refactor|restructure|redesign|rearchitect|migrate)\b",
    r"\b(implement|build|create)\s+.{20,}",  # long descriptions = complex
    r"\b(multi.?file|across\s+(files|modules|components|services|microservices|the\s+\w+))\b",
    r"\b(security|auth\w*|encrypt|permission|access\s+control)\b",
    r"\b(database|schema|migration|model)\s+(design|change|update)",
    r"\b(CI|CD|pipeline|deploy|infrastructure)\b",
    r"\b(performance|optimiz\w+|cache|caching|concurrent)\b",
    r"\b(test\s+suite|integration\s+test|e2e)\b",
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


def classify_task(prompt: str) -> dict:
    """Classify a user prompt into a task category.

    Returns dict with:
        category: trivial | research | standard | complex
        effort: low | medium | high
        model_hint: haiku | sonnet | opus
        confidence: float 0-1
    """
    text = prompt.lower().strip()

    # Short prompts are likely trivial
    if len(text) < 20:
        for pattern in TRIVIAL_PATTERNS:
            if re.search(pattern, text):
                return _result("trivial", 0.9)
        # Very short but no pattern match — probably a quick command
        return _result("trivial", 0.5)

    # Check trivial patterns
    trivial_matches = sum(1 for p in TRIVIAL_PATTERNS if re.search(p, text))
    if trivial_matches >= 2:
        return _result("trivial", 0.9)
    if trivial_matches == 1 and len(text) < 60:
        return _result("trivial", 0.7)

    # Check complex patterns
    complex_matches = sum(1 for p in COMPLEX_PATTERNS if re.search(p, text))
    if complex_matches >= 2:
        return _result("complex", 0.8)
    if complex_matches == 1 and len(text) > 40:
        return _result("complex", 0.6)

    # Check research patterns
    research_matches = sum(1 for p in RESEARCH_PATTERNS if re.search(p, text))
    if research_matches >= 2:
        return _result("research", 0.8)
    if research_matches == 1:
        return _result("research", 0.6)

    # Default: standard
    return _result("standard", 0.5)


def _result(category: str, confidence: float) -> dict:
    return {
        "category": category,
        "effort": EFFORT_MAP[category],
        "model_hint": MODEL_HINT_MAP[category],
        "confidence": confidence,
    }
