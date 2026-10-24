"""List code lines in lessons that are too wide for a phone.

Usage: python3 tools/check_code_width.py [lesson-id]

Checks every line inside <pre><code ...> blocks (solutions included),
after HTML-unescaping. Exits 1 if any line is longer than LIMIT.
"""
import html
import pathlib
import re
import sys

LIMIT = 39  # measured: 39 chars of 14px monospace fit a 390px phone
ROOT = pathlib.Path(__file__).resolve().parent.parent
CODE = re.compile(r"<pre><code[^>]*>(.*?)</code></pre>", re.S)


def main():
    ids = sys.argv[1:]
    files = ([ROOT / "lessons" / f"{i}.html" for i in ids]
             or sorted((ROOT / "lessons").glob("*.html")))
    bad = 0
    for f in files:
        text = f.read_text()
        for m in CODE.finditer(text):
            first = text.count("\n", 0, m.start(1)) + 1
            for k, line in enumerate(m.group(1).split("\n")):
                line = html.unescape(line).rstrip()
                if len(line) > LIMIT:
                    bad += 1
                    print(f"{f.stem}:{first + k}: {len(line)}: {line}")
    if bad:
        print(f"{bad} line(s) longer than {LIMIT} characters")
        sys.exit(1)
    print(f"OK: all code lines fit in {LIMIT} characters")


if __name__ == "__main__":
    main()
