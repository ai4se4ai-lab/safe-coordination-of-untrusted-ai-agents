"""Inline every \\input of docs/paper/main.tex into docs/paper/main-flat.tex.

Journal submission systems often require a single source file. The flattened file is
derived; edit main.tex, sections/*.tex and the generators instead.
"""
from pathlib import Path
import re

PAPER = Path(__file__).resolve().parents[1] / "docs/paper"


def expand(text, depth=0):
    if depth > 5:
        raise RecursionError("nested \\input too deep")

    def repl(match):
        name = match.group(1)
        path = PAPER / (name if name.endswith(".tex") else name + ".tex")
        body = path.read_text(encoding="utf-8")
        return "%% BEGIN inlined %s\n%s\n%% END inlined %s\n" % (name, expand(body, depth + 1), name)

    return re.sub(r"^\\input\{([^}]+)\}", repl, text, flags=re.M)


def main():
    flat = expand((PAPER / "main.tex").read_text(encoding="utf-8"))
    (PAPER / "main-flat.tex").write_text(flat, encoding="utf-8")
    print(PAPER / "main-flat.tex", len(flat.splitlines()), "lines")


if __name__ == "__main__":
    main()
