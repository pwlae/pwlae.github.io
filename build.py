#!/usr/bin/env python3
"""Build index.html from curriculum.json + lessons/*.html + template.html.

Usage:  python3 build.py

Needs: Python 3.10+, Pygments (pip install pygments), and for diagrams
Node + `npm install` (mermaid-cli). Diagrams are cached in diagrams/ by hash,
so only new or changed diagrams are rendered.

Lesson files use a few custom tags that this script expands (see CLAUDE.md):
  <pre><code class="language-python">...</code></pre>   -> highlighted code
  <pre class="mermaid" data-alt="...">...</pre>          -> diagrams/<hash>.svg image
  <fact title="...">...</fact>                          -> "Interesting fact" expandable
  <leetcode slug=".." num=".." title=".." level="Easy" minutes="10">
     <hint>...</hint> <solution>...</solution>
  </leetcode>                                           -> LeetCode card
  <recap>...</recap>                                    -> "Remember" box
"""
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

try:
    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_by_name
except ImportError:
    sys.exit("Pygments is missing. Run: pip install pygments")

ROOT = Path(__file__).resolve().parent
LESSONS = ROOT / "lessons"
DIAGRAMS = ROOT / "diagrams"
TOOLS = ROOT / "tools"
LEETCODE_URL = "https://leetcode.com/problems/{}/"
LEVELS = {"Easy", "Medium", "Hard"}

# LeetCode mark from Simple Icons (CC0). Used only to label links to LeetCode.
LEETCODE_SVG = (
    '<svg class="lc-logo" viewBox="0 0 24 24" aria-hidden="true"><path d="M13.483 0a1.374 1.374 0 0 0-.961.438L7.116 6.226l-3.854 4.126a5.266 5.266 0 0 0-1.209 2.104 5.35 5.35 0 0 0-.125.513 5.527 5.527 0 0 0 .062 2.362 5.83 5.83 0 0 0 .349 1.017 5.938 5.938 0 0 0 1.271 1.818l4.277 4.193.039.038c2.248 2.165 5.852 2.133 8.063-.074l2.396-2.392c.54-.54.54-1.414.003-1.955a1.378 1.378 0 0 0-1.951-.003l-2.396 2.392a3.021 3.021 0 0 1-4.205.038l-.02-.019-4.276-4.193c-.652-.64-.972-1.469-.948-2.263a2.68 2.68 0 0 1 .066-.523 2.545 2.545 0 0 1 .619-1.164L9.13 8.114c1.058-1.134 3.204-1.27 4.43-.278l3.501 2.831c.593.48 1.461.387 1.94-.207a1.384 1.384 0 0 0-.207-1.943l-3.5-2.831c-.8-.647-1.766-1.045-2.774-1.202l2.015-2.158A1.384 1.384 0 0 0 13.483 0zm-2.866 12.815a1.38 1.38 0 0 0-1.38 1.382 1.38 1.38 0 0 0 1.38 1.382H20.79a1.38 1.38 0 0 0 1.38-1.382 1.38 1.38 0 0 0-1.38-1.382z"/></svg>'
)


class BuildError(Exception):
    pass


CARD_IDS = set()  # a problem can appear in more than one lesson; only the first card gets the id


def attrs(s):
    return {k: html.unescape(v) for k, v in re.findall(r'([\w-]+)="([^"]*)"', s)}


def esc(s):
    return html.escape(s, quote=True)


# ---------- code highlighting ----------

def render_code(lang, code):
    code = html.unescape(code).strip("\n")
    try:
        lexer = get_lexer_by_name(lang)
    except Exception:
        raise BuildError(f"unknown code language: {lang}")
    body = highlight(code, lexer, HtmlFormatter(nowrap=True))
    return f'<pre class="code" data-lang="{esc(lang)}"><code>{body.rstrip()}</code></pre>'


def expand_code(text):
    return re.sub(
        r'<pre><code class="language-([\w+-]+)">(.*?)</code></pre>',
        lambda m: render_code(m.group(1), m.group(2)),
        text,
        flags=re.S,
    )


# ---------- diagrams ----------

def mermaid_config_hash():
    h = hashlib.sha1()
    for name in ("mermaid.json", "puppeteer.json"):
        h.update((TOOLS / name).read_bytes())
    h.update((ROOT / "package.json").read_bytes())
    return h.hexdigest()


def find_chrome():
    for env in ("PUPPETEER_EXECUTABLE_PATH", "CHROME_PATH"):
        if os.environ.get(env):
            return os.environ[env]
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        p = shutil.which(name)
        if p:
            return p
    return None


class Diagrams:
    def __init__(self):
        self.cfg = mermaid_config_hash()
        self.used = set()
        self.rendered = 0
        DIAGRAMS.mkdir(exist_ok=True)

    def render(self, source, alt):
        source = html.unescape(source).strip("\n")
        if not alt:
            raise BuildError("every <pre class=\"mermaid\"> needs data-alt=\"...\" (text for screen readers)")
        key = hashlib.sha1((self.cfg + source).encode()).hexdigest()[:12]
        out = DIAGRAMS / f"{key}.svg"
        if not out.exists():
            self._mmdc(source, out)
            self.rendered += 1
        self.used.add(out.name)
        w, h = svg_size(out)
        src = f"diagrams/{out.name}"
        return (
            f'<figure class="diagram"><a href="{src}" target="_blank" rel="noopener" title="Open full size">'
            f'<img src="{src}" alt="{esc(alt)}" width="{w}" height="{h}" loading="lazy" decoding="async"></a>'
            f"</figure>"
        )

    def _mmdc(self, source, out):
        mmdc = ROOT / "node_modules" / ".bin" / "mmdc"
        if not mmdc.exists():
            raise BuildError("mermaid-cli is missing. Run: PUPPETEER_SKIP_DOWNLOAD=1 npm install")
        env = dict(os.environ)
        chrome = find_chrome()
        if chrome and "PUPPETEER_EXECUTABLE_PATH" not in env:
            env["PUPPETEER_EXECUTABLE_PATH"] = chrome
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "d.mmd"
            src.write_text(source)
            tmp_out = Path(tmp) / "d.svg"
            r = subprocess.run(
                [str(mmdc), "-q", "-i", str(src), "-o", str(tmp_out),
                 "-c", str(TOOLS / "mermaid.json"), "-p", str(TOOLS / "puppeteer.json"), "-b", "white"],
                capture_output=True, text=True, env=env,
            )
            if r.returncode != 0 or not tmp_out.exists():
                raise BuildError(f"mermaid failed for diagram:\n{source}\n{r.stderr[-1500:]}")
            out.write_text(tmp_out.read_text())

    def prune(self):
        for f in DIAGRAMS.glob("*.svg"):
            if f.name not in self.used:
                f.unlink()


def svg_size(path):
    head = path.read_text()[:3000]
    m = re.search(r'viewBox="[-\d.]+ [-\d.]+ ([\d.]+) ([\d.]+)"', head)
    if not m:
        return 600, 300
    return round(float(m.group(1))), round(float(m.group(2)))


def expand_mermaid(text, diagrams):
    def repl(m):
        a = attrs(m.group(1))
        return diagrams.render(m.group(2), a.get("data-alt", ""))

    return re.sub(r'<pre class="mermaid"([^>]*)>(.*?)</pre>', repl, text, flags=re.S)


# ---------- custom blocks ----------

def expand_facts(text):
    def repl(m):
        title = attrs(m.group(1)).get("title", "")
        label = "Interesting fact" + (f": {esc(title)}" if title else "")
        return f'<details class="fact"><summary>{label}</summary><div>{m.group(2).strip()}</div></details>'

    return re.sub(r"<fact([^>]*)>(.*?)</fact>", repl, text, flags=re.S)


def expand_recap(text):
    return re.sub(
        r"<recap>(.*?)</recap>",
        lambda m: f'<aside class="recap"><h3>Remember</h3>{m.group(1).strip()}</aside>',
        text,
        flags=re.S,
    )


def expand_leetcode(text, lesson_id, problems):
    """Returns (text, answers_html). Solutions also go to a print-only answers list."""
    answers = []

    def repl(m):
        a = attrs(m.group(1))
        inner = m.group(2)
        for k in ("slug", "num", "title", "level"):
            if not a.get(k):
                raise BuildError(f"<leetcode> in {lesson_id} is missing {k}=")
        if a["level"] not in LEVELS:
            raise BuildError(f"<leetcode {a['slug']}> level must be one of {LEVELS}")
        url = LEETCODE_URL.format(a["slug"])
        problems.append(a["slug"])
        card_id = "" if a["slug"] in CARD_IDS else f' id="p-{esc(a["slug"])}"'
        CARD_IDS.add(a["slug"])
        n = len(answers) + 1
        hint = re.search(r"<hint>(.*?)</hint>", inner, re.S)
        sol = re.search(r"<solution>(.*?)</solution>", inner, re.S)
        minutes = a.get("minutes")
        meta = f'<span class="lvl lvl-{a["level"].lower()}">{a["level"]}</span>'
        if minutes:
            meta += f' <span class="mins">~{esc(minutes)} min</span>'
        parts = [
            f'<div class="lc"{card_id}>',
            f'<a class="lc-link" href="{url}" rel="noopener" target="_blank">'
            f'{LEETCODE_SVG}<span class="lc-name">LeetCode</span>'
            f'<span class="lc-title">{esc(a["num"])}. {esc(a["title"])}</span></a>',
            f'<div class="lc-meta">{meta}'
            f'<label class="solved"><input type="checkbox" data-slug="{esc(a["slug"])}"> Solved</label>'
            f'<span class="print-only">&#9744; solved &middot; {url}</span></div>',
        ]
        if hint:
            parts.append(f'<details class="hint"><summary>Hint</summary><div>{hint.group(1).strip()}</div></details>')
        if sol:
            parts.append(
                f'<details class="solution"><summary>Solution</summary><div>{sol.group(1).strip()}</div></details>'
            )
            answers.append(f'<li><b>{esc(a["num"])}. {esc(a["title"])}</b>{sol.group(1).strip()}</li>')
        else:
            answers.append(None)
        parts.append("</div>")
        return "".join(parts)

    text = re.sub(r"<leetcode([^>]*)>(.*?)</leetcode>", repl, text, flags=re.S)
    real = [x for x in answers if x]
    answers_html = ""
    if real:
        answers_html = '<section class="answers"><h3>Answers</h3><ol>' + "".join(real) + "</ol></section>"
    return text, answers_html


# ---------- page ----------

def roadmap_source(cur, written):
    """A top-down chain of stages (narrow enough for a phone). Each box lists
    its lessons; a stage with nothing written yet is drawn dashed."""
    lines = ["flowchart TD"]
    soon = []
    for si, s in enumerate(cur["stages"]):
        rows = [s["title"].upper()]
        ids = []
        for i, l in enumerate(cur["lessons"]):
            if l["stage"] == s["id"]:
                rows.append(f"{i}. {l['title']}")
                ids.append(l["id"])
        label = "<br/>".join(rows).replace('"', "'")
        lines.append(f'  S{si}["{label}"]')
        if si:
            lines.append(f"  S{si - 1} --> S{si}")
        if not any(i in written for i in ids):
            soon.append(f"S{si}")
    if soon:
        lines.append("  classDef soon stroke-dasharray: 5 4,color:#666")
        lines.append(f"  class {','.join(soon)} soon")
    return "\n".join(lines)


def validate(cur):
    stages = {s["id"] for s in cur["stages"]}
    seen = set()
    for l in cur["lessons"]:
        if l["stage"] not in stages:
            raise BuildError(f"lesson {l['id']}: unknown stage {l['stage']}")
        for r in l["requires"]:
            if r not in seen:
                raise BuildError(f"lesson {l['id']} requires {r}, which must come earlier in curriculum.json")
        seen.add(l["id"])


def build():
    cur = json.loads((ROOT / "curriculum.json").read_text())
    validate(cur)
    stage_title = {s["id"]: s["title"] for s in cur["stages"]}
    by_id = {l["id"]: l for l in cur["lessons"]}
    written = {l["id"] for l in cur["lessons"] if (LESSONS / f"{l['id']}.html").exists()}
    for f in LESSONS.glob("*.html"):
        if f.stem not in by_id:
            raise BuildError(f"{f.name} is not listed in curriculum.json")

    diagrams = Diagrams()
    articles, all_problems = [], []
    order = cur["lessons"]
    for i, l in enumerate(order):
        if l["id"] not in written:
            continue
        try:
            body = (LESSONS / f"{l['id']}.html").read_text()
            problems = []
            body = expand_mermaid(body, diagrams)
            body, answers = expand_leetcode(body, l["id"], problems)
            body = expand_code(body)
            answers = expand_code(answers)
            body = expand_facts(body)
            body = expand_recap(body)
        except BuildError as e:
            raise BuildError(f"lessons/{l['id']}.html: {e}")
        all_problems += problems
        reqs = ", ".join(f'<a href="#{r}">{esc(by_id[r]["title"])}</a>' for r in l["requires"])
        nxt = next((o for o in order[i + 1:] if o["id"] in written), None)
        meta = [esc(stage_title[l["stage"]])]
        if problems:
            meta.append(f'<span class="lesson-progress" data-lesson="{l["id"]}">{len(problems)} problem{"s" if len(problems) != 1 else ""}</span>')
        foot = '<a href="#map">&uarr; Map</a>'
        if nxt:
            foot += f' &middot; Next: <a href="#{nxt["id"]}">{esc(nxt["title"])}</a>'
        articles.append(
            f'<article id="{l["id"]}" data-problems="{" ".join(problems)}">'
            f'<header class="lesson-head"><p class="kicker">Lesson {i} &middot; {" &middot; ".join(meta)}</p>'
            f'<h2>{esc(l["title"])}</h2>'
            + (f'<p class="requires">Read first: {reqs}</p>' if reqs else "")
            + f'<button type="button" class="print-btn" data-print="{l["id"]}">Print this lesson / Save as PDF</button>'
            f"</header>{body}{answers}"
            f'<p class="lesson-foot no-print">{foot}</p></article>'
        )

    dupes = {p for p in all_problems if all_problems.count(p) > 1}
    if dupes:
        print(f"note: problems used in more than one lesson: {', '.join(sorted(dupes))}")

    toc = []
    for s in cur["stages"]:
        items = []
        for i, l in enumerate(order):
            if l["stage"] != s["id"]:
                continue
            if l["id"] in written:
                items.append(f'<li><a href="#{l["id"]}">{i}. {esc(l["title"])}</a> <span class="toc-progress" data-lesson="{l["id"]}"></span></li>')
            else:
                items.append(f'<li class="soon">{i}. {esc(l["title"])} <small>(coming soon)</small></li>')
        toc.append(f"<li><b>{esc(s['title'])}</b><ul>{''.join(items)}</ul></li>")
    roadmap = diagrams.render(roadmap_source(cur, written), "Map of all lessons. Arrows point from a lesson to the lessons that build on it.")
    diagrams.prune()

    page = (ROOT / "template.html").read_text()
    pygments_css = (TOOLS / "code.css").read_text()
    repl = {
        "{{TITLE}}": esc(cur["title"]),
        "{{TAGLINE}}": esc(cur["tagline"]),
        "{{CODE_CSS}}": pygments_css,
        "{{ROADMAP}}": roadmap,
        "{{TOC}}": f'<ol class="toc">{"".join(toc)}</ol>',
        "{{LESSONS}}": "\n".join(articles),
        "{{TOTAL_PROBLEMS}}": str(len(set(all_problems))),
        "{{DIAGRAMS}}": json.dumps(sorted(f"diagrams/{n}" for n in diagrams.used)),
        "{{UPDATED}}": date.today().isoformat(),
    }
    for k, v in repl.items():
        page = page.replace(k, v)
    (ROOT / "index.html").write_text(page)
    print(
        f"built index.html: {len(written)}/{len(order)} lessons, {len(set(all_problems))} problems, "
        f"{len(diagrams.used)} diagrams ({diagrams.rendered} newly rendered), {len(page) // 1024} KB"
    )


if __name__ == "__main__":
    try:
        build()
    except BuildError as e:
        sys.exit(f"build failed: {e}")
