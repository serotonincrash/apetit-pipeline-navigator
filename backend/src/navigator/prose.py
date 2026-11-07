"""The writing standards' banned patterns and word limits, as a check on one piece of text."""

import re

_TOKEN = re.compile(r"\{\{.*?\}\}", re.DOTALL)

_BANNED_WORDS = [
    # filler
    "genuinely",
    "honestly",
    "straightforward",
    "seamless",
    "robust",
    "leverage",
    "delve",
    "crucial",
    "comprehensive",
    # inflated
    "highlights",
    "underscores",
    "showcases",
    "landscape",
    "ensure",
    "foster",
    "empower",
    "unlock",
    "actionable",
    # vague amounts
    "various",
    "several",
]
_BANNED_PHRASES = ["plays a key role", "a number of", "and more"]
_BANNED = re.compile(
    r"\b(" + "|".join([*_BANNED_WORDS, *(re.escape(p) for p in _BANNED_PHRASES)]) + r")\b",
    re.IGNORECASE,
)
_SYMBOLS = re.compile(r"[\u00d7\u2192\u2260\u2265\u2264]|~\s*\d")
_NOT_BUT = re.compile(r"\bnot\b[^.;!?]{1,80}?,?\s+\bbut\b", re.IGNORECASE)
_NOT_JUST = re.compile(r"\bnot just\b[^.;!?]{1,80}?,\s*(it|they|this)\b", re.IGNORECASE)


def check(text: str, max_words: int | None = None) -> list[str]:
    """Return the problems found in `text`, in plain words. Text inside {{...}} is ignored."""
    plain = _TOKEN.sub(" ", text)
    problems: list[str] = []
    if "—" in plain:
        problems.append("Contains an em dash. Use a full stop, a comma or brackets.")
    for symbol in dict.fromkeys(_SYMBOLS.findall(plain)):
        problems.append(f"Uses the symbol {symbol!r} in a sentence. Write it out in words.")
    for word in dict.fromkeys(w.lower() for w in _BANNED.findall(plain)):
        problems.append(f"Uses the banned word or phrase '{word}'.")
    if "!" in plain:
        problems.append("Contains an exclamation mark.")
    if _NOT_BUT.search(plain) or _NOT_JUST.search(plain):
        problems.append("Uses a 'not X but Y' construction. State what is true.")
    if max_words is not None:
        count = len(text.split())
        if count > max_words:
            problems.append(f"Has {count} words, over the limit of {max_words}.")
    return problems
