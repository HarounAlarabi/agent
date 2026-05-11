"""ClaimGuard — enforce proof requirements on completion claims.

Strong completion verbs ("built", "launched", …) must be accompanied by one of:
  • a GitHub / live URL
  • a screenshot or image reference
  • a code snippet (``` block)
  • a demo description ("demo", "live at", "try it", …)
  • a measurable outcome (numbers + concrete units)

If none of the above are found the claim is automatically downgraded to an
in-progress form ("working on", "building", "experimenting with", …).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ── Proof-marker patterns ─────────────────────────────────────────────────────

_PROOF_RE = re.compile(
    r"""
    github\.com                                     # GitHub link
    | github\.io
    | ```[\s\S]*?```                                # code block
    | \bscreenshot\b                                # screenshot reference
    | \bsee\s+image\b
    | \battached\b
    | \bdemo\s+at\b | \bdemo:\b | \blive\s+at\b    # demo/live
    | \btry\s+it\b | \bcheck\s+it\s+out\b
    | https?://\S{10,}                              # any real URL (≥10 chars)
    | \d[\d,]*\s*\+?\s*(?:                          # measurable outcomes
        users?|downloads?|stars?|revenue|customers?
        |signups?|installs?|views?|subscribers?|followers?
        |sales?|conversions?|visits?
      )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Arabic proof markers
_PROOF_AR_RE = re.compile(
    r"""
    github\.com | github\.io | https?://\S{10,}
    | لقطة\s*شاشة                     # screenshot
    | صورة\s*توضيحية
    | تجريبي | عرض\s*مباشر            # demo
    | \d[\d,]*\s*(?:مستخدم|تحميل|نجم|عميل|متابع)
    """,
    re.IGNORECASE | re.VERBOSE,
)


# ── English claim → downgrade substitutions ───────────────────────────────────

# Order matters: more specific patterns first.
_EN_SUBS: list[tuple[re.Pattern, str]] = [
    # "I've built / we've built / I've created …" — contractions first
    (re.compile(r"\b(I've|we've)\s+built\b", re.I), r"\1 been building"),
    (re.compile(r"\b(I've|we've)\s+created\b", re.I), r"\1 been working on creating"),
    (re.compile(r"\b(I've|we've)\s+launched\b", re.I), r"\1 been working on launching"),
    (re.compile(r"\b(I've|we've)\s+shipped\b", re.I), r"\1 been testing"),
    (re.compile(r"\b(I've|we've)\s+finished\b", re.I), r"\1 been working on"),
    (re.compile(r"\b(I've|we've)\s+completed\b", re.I), r"\1 been working on"),
    (re.compile(r"\b(I've|we've)\s+released\b", re.I), r"\1 been working on releasing"),
    (re.compile(r"\b(I've|we've)\s+deployed\b", re.I), r"\1 been experimenting with deploying"),
    (re.compile(r"\b(I've|we've)\s+delivered\b", re.I), r"\1 been working on delivering"),
    (re.compile(r"\b(I've|we've)\s+published\b", re.I), r"\1 been working on publishing"),
    # "I built / we built …"
    (re.compile(r"\b(I|we)\s+built\b", re.I), r"\1'm building"),
    (re.compile(r"\b(I|we)\s+created\b", re.I), r"\1'm creating"),
    (re.compile(r"\b(I|we)\s+launched\b", re.I), r"\1'm working on launching"),
    (re.compile(r"\b(I|we)\s+shipped\b", re.I), r"\1'm testing"),
    (re.compile(r"\b(I|we)\s+finished\b", re.I), r"\1'm working on"),
    (re.compile(r"\b(I|we)\s+completed\b", re.I), r"\1'm working on"),
    (re.compile(r"\b(I|we)\s+released\b", re.I), r"\1'm working on releasing"),
    (re.compile(r"\b(I|we)\s+deployed\b", re.I), r"\1'm experimenting with deploying"),
    (re.compile(r"\b(I|we)\s+delivered\b", re.I), r"\1'm working on delivering"),
    (re.compile(r"\b(I|we)\s+published\b", re.I), r"\1'm working on publishing"),
    # Sentence-starter / passive participle: "Built X in …", "Launched Y …"
    (re.compile(r"(?<!['\w])Built\b"), "Building"),
    (re.compile(r"(?<!['\w])Created\b"), "Creating"),
    (re.compile(r"(?<!['\w])Launched\b"), "Working on launching"),
    (re.compile(r"(?<!['\w])Shipped\b"), "Testing"),
    (re.compile(r"(?<!['\w])Finished\b"), "Working on"),
    (re.compile(r"(?<!['\w])Completed\b"), "Working on"),
    (re.compile(r"(?<!['\w])Released\b"), "Working on releasing"),
    (re.compile(r"(?<!['\w])Deployed\b"), "Experimenting with deploying"),
    (re.compile(r"(?<!['\w])Delivered\b"), "Working on delivering"),
    (re.compile(r"(?<!['\w])Published\b"), "Working on publishing"),
]

# ── English detection pattern ─────────────────────────────────────────────────

_EN_CLAIM_RE = re.compile(
    r"\b(?:built|created|launched|shipped|finished|completed|released|deployed|delivered|published)\b",
    re.IGNORECASE,
)

# ── Arabic claim → downgrade substitutions ────────────────────────────────────

_AR_SUBS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"بنيت\b"), "أعمل على بناء"),
    (re.compile(r"بنينا\b"), "نعمل على بناء"),
    (re.compile(r"أنشأت\b"), "أعمل على إنشاء"),
    (re.compile(r"أنشأنا\b"), "نعمل على إنشاء"),
    (re.compile(r"أطلقت\b"), "أعمل على إطلاق"),
    (re.compile(r"أطلقنا\b"), "نعمل على إطلاق"),
    (re.compile(r"أكملت\b"), "أعمل على إكمال"),
    (re.compile(r"أكملنا\b"), "نعمل على إكمال"),
    (re.compile(r"انتهيت\b"), "أعمل على"),
    (re.compile(r"انتهينا\b"), "نعمل على"),
    (re.compile(r"نشرت\b"), "أعمل على نشر"),
    (re.compile(r"نشرنا\b"), "نعمل على نشر"),
    (re.compile(r"أصدرت\b"), "أعمل على إصدار"),
    (re.compile(r"أصدرنا\b"), "نعمل على إصدار"),
    (re.compile(r"سلّمت\b"), "أعمل على تسليم"),
    (re.compile(r"سلّمنا\b"), "نعمل على تسليم"),
    (re.compile(r"أنجزت\b"), "أعمل على إنجاز"),
    (re.compile(r"أنجزنا\b"), "نعمل على إنجاز"),
    (re.compile(r"شحنت\b"), "أختبر"),
    (re.compile(r"شحننا\b"), "نختبر"),
]

_AR_CLAIM_RE = re.compile(
    r"بنيت|بنينا|أنشأت|أنشأنا|أطلقت|أطلقنا|أكملت|أكملنا"
    r"|انتهيت|انتهينا|نشرت|نشرنا|أصدرت|أصدرنا"
    r"|سلّمت|سلّمنا|أنجزت|أنجزنا|شحنت|شحننا"
)


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class GuardResult:
    text: str
    was_downgraded: bool
    claims_found: list[str] = field(default_factory=list)

    @property
    def notice(self) -> str:
        if not self.was_downgraded:
            return ""
        unique = sorted(set(self.claims_found))
        claims_str = ", ".join(f'"{c}"' for c in unique)
        return (
            f"Completion claim(s) {claims_str} were downgraded to in-progress language "
            "because no proof was detected (GitHub link, screenshot, code snippet, "
            "demo, or measurable outcome)."
        )


# ── Main class ────────────────────────────────────────────────────────────────

class ClaimGuard:
    """Validate and optionally downgrade unsupported completion claims."""

    def validate(self, text: str) -> GuardResult:
        """Return the text, possibly with claims downgraded, plus metadata."""
        is_arabic = bool(re.search(r"[؀-ۿ]", text))
        claim_re = _AR_CLAIM_RE if is_arabic else _EN_CLAIM_RE
        proof_re = _PROOF_AR_RE if is_arabic else _PROOF_RE

        claims = claim_re.findall(text)
        if not claims:
            return GuardResult(text=text, was_downgraded=False)

        if proof_re.search(text):
            return GuardResult(text=text, was_downgraded=False, claims_found=claims)

        downgraded = self._downgrade(text, is_arabic)
        return GuardResult(text=downgraded, was_downgraded=True, claims_found=claims)

    @staticmethod
    def _downgrade(text: str, is_arabic: bool) -> str:
        subs = _AR_SUBS if is_arabic else _EN_SUBS
        for pattern, replacement in subs:
            text = pattern.sub(replacement, text)
        return text
