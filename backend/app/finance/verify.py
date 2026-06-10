"""Citation-faithfulness verification: no number reaches the user unbacked.

After generation, every numeric token in the draft answer must correspond to a
verified source value (a fact or a computed metric) within tolerance. Matching
accounts for presentation variants — scale words ("$3.2 billion" for
3_200_000_000), percents, thousands separators, and rounding to 0–2 decimals.

Deliberately conservative in what it IGNORES (years, citation markers [n],
small ordinals) and strict about everything else: an unmatched number means the
answer is flagged/rejected, because a fabricated figure is the one failure mode
this system must not have.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

_REL_TOLERANCE = Decimal("0.005")  # 0.5% — absorbs narration rounding

_NUMBER_RE = re.compile(
    r"(?<![\w.])"  # not inside a word/identifier
    r"\$?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"
    r"\s*(billion|million|thousand|bn|mm|m|k|b)?\s*(%|percent)?",
    re.I,
)

_SCALE_WORDS = {
    "thousand": Decimal(1_000), "k": Decimal(1_000),
    "million": Decimal(1_000_000), "mm": Decimal(1_000_000), "m": Decimal(1_000_000),
    "billion": Decimal(1_000_000_000), "bn": Decimal(1_000_000_000),
    "b": Decimal(1_000_000_000),
}

_CITATION_RE = re.compile(r"\[\d+\]")
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")


@dataclass(slots=True)
class NumberMention:
    raw: str  # as written, e.g. "$3.2 billion"
    value: Decimal  # resolved, e.g. 3200000000
    is_percent: bool


def extract_numbers(text: str) -> list[NumberMention]:
    """Numeric claims in a draft answer, with scale words resolved. Citation
    markers, fiscal years, and Q1–Q4 style ordinals are not claims."""
    cleaned = _CITATION_RE.sub("", text)
    cleaned = re.sub(r"\b(?:Q[1-4]|FY\s?\d{4})\b", "", cleaned, flags=re.I)
    mentions: list[NumberMention] = []
    for m in _NUMBER_RE.finditer(cleaned):
        digits, scale_word, pct = m.group(1), m.group(2), m.group(3)
        bare = digits.replace(",", "")
        if _YEAR_RE.match(bare) and not scale_word and not pct and "$" not in m.group(0):
            continue
        value = Decimal(bare)
        if scale_word:
            value *= _SCALE_WORDS[scale_word.lower()]
        mentions.append(
            NumberMention(raw=m.group(0).strip(), value=value, is_percent=bool(pct))
        )
    return mentions


def _matches(mention: NumberMention, allowed: Decimal) -> bool:
    """Does a written number plausibly present the allowed value?"""
    candidates = [allowed, -allowed]
    # A value may be narrated at a different scale than stored ("4,200" for
    # a fact stored in dollars as 4,200,000,000 would NOT match — but
    # "$4.2 billion" resolves to the stored magnitude, so only the resolved
    # mention is compared; we additionally allow per-scale renditions.
    for scale in (Decimal(1_000), Decimal(1_000_000), Decimal(1_000_000_000)):
        candidates.extend([allowed / scale, -allowed / scale])
    for cand in candidates:
        bound = max(abs(cand), Decimal(1)) * _REL_TOLERANCE
        # Also accept rounding to whole/one/two decimals of the candidate.
        if abs(mention.value - cand) <= max(bound, Decimal("0.05")):
            return True
    return False


def unverified_numbers(
    text: str, allowed_values: Iterable[Decimal]
) -> list[NumberMention]:
    """Numeric claims in `text` not backed by any allowed value (empty == clean)."""
    allowed = list(allowed_values)
    return [
        m for m in extract_numbers(text)
        if not any(_matches(m, a) for a in allowed)
    ]


def is_faithful(text: str, allowed_values: Iterable[Decimal]) -> bool:
    return not unverified_numbers(text, allowed_values)
