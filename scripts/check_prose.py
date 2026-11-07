"""Check the writing standards on step summaries, section annotations, prompts and UI strings.

Prints `file:line: problem` for each breach and exits 1 if there is any. Run it with
`uv run --project backend python scripts/check_prose.py`.
"""

import ast
import re
import sys
from pathlib import Path

from navigator.prose import check

ROOT = Path(__file__).resolve().parents[1]
STEPS = ROOT / "backend" / "src" / "navigator" / "steps"
PROMPTS = ROOT / "backend" / "src" / "navigator" / "agents" / "prompts"
FRONTEND = ROOT / "frontend" / "src"

SUMMARY_WORDS = 40
SECTION_WORDS = 25
# A quoted phrase of three or more words that starts with a capital: UI copy, not a class list.
UI_STRING = re.compile(r"""(["'`])([A-Z][^"'`\n]*(?: [^"'`\n]+){2,})\1""")


def _text(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def annotations(path: Path) -> list[tuple[int, str, int]]:
    """Each annotation in a step file as (line, text, word limit)."""
    found: list[tuple[int, str, int]] = []
    for node in ast.walk(ast.parse(path.read_text())):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name == "step":
            for keyword in node.keywords:
                text = _text(keyword.value)
                if keyword.arg == "summary" and text is not None:
                    found.append((keyword.value.lineno, text, SUMMARY_WORDS))
        elif name == "section":
            candidates = [node.args[1]] if len(node.args) > 1 else []
            candidates += [k.value for k in node.keywords if k.arg == "annotation"]
            for candidate in candidates:
                text = _text(candidate)
                if text is not None:
                    found.append((candidate.lineno, text, SECTION_WORDS))
    return found


def main() -> int:
    breaches: list[str] = []

    def report(path: Path, line: int, text: str, max_words: int | None) -> None:
        for problem in check(text, max_words):
            breaches.append(f"{path.relative_to(ROOT)}:{line}: {problem}")

    for path in sorted(STEPS.glob("*.py")):
        for line, text, limit in annotations(path):
            report(path, line, text, limit)

    if PROMPTS.is_dir():
        for path in sorted(p for p in PROMPTS.rglob("*") if p.is_file()):
            for number, line in enumerate(path.read_text().splitlines(), start=1):
                report(path, number, line, None)

    if FRONTEND.is_dir():
        for path in sorted([*FRONTEND.rglob("*.ts"), *FRONTEND.rglob("*.tsx")]):
            for number, line in enumerate(path.read_text().splitlines(), start=1):
                if line.lstrip().startswith(("import ", "//", "*", "/*")):
                    continue
                for match in UI_STRING.finditer(line):
                    report(path, number, match.group(2), None)

    if breaches:
        print("\n".join(breaches))
    return 1 if breaches else 0


if __name__ == "__main__":
    sys.exit(main())
