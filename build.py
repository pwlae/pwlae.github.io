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


PAGES = ROOT / "l"  # one generated page per lesson

# The one photo on the site (home page only, hidden in print). Public domain,
# from Wikimedia Commons; crediting the photographer anyway.
HERO = (
    '<figure class="hero no-print"><img src="images/tube.webp" width="780" height="438" decoding="async" '
    'alt="A red Northern line train coming out of a round tunnel onto the tracks.">'
    '<figcaption>Northern line train leaving the tunnel near Hendon Central. Photo: SPSmiler, '
    '<a href="https://commons.wikimedia.org/wiki/File:Why_London_Underground_is_nicknamed_The_Tube.jpg" '
    'rel="noopener">public domain</a>.</figcaption></figure>'
)


def link_rewriter(home_of_problem, here):
    """In a lesson page, '#<lesson>' becomes '<lesson>.html' and '#p-<slug>'
    points at the page that has that problem card."""
    def repl(m):
        target = m.group(1)
        if target.startswith("p-"):
            page = home_of_problem.get(target[2:])
            if page and page != here:
                return f'href="{page}.html#{target}"'
            return m.group(0)
        if target in LESSON_IDS:
            return f'href="{target}.html"'
        return m.group(0)

    return lambda text: re.sub(r'href="#([\w-]+)"', repl, text)


LESSON_IDS = set()


def first_text(html_text, limit=200):
    """Plain text of the lesson's lead paragraph, for meta descriptions."""
    m = re.search(r'<p class="lead">(.*?)</p>', html_text, re.S)
    text = html.unescape(re.sub(r"<[^>]+>", "", m.group(1) if m else ""))
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return text


def git_date(path):
    """Date of the last commit that touched a file (for the sitemap)."""
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", str(path)],
                             cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        out = ""
    return out or date.today().isoformat()


def head_tags(site, url, title, desc, kind):
    """Description, canonical URL and link-preview (Open Graph) tags."""
    image = site["url"] + "images/og.jpg"
    tags = [
        f'<meta name="description" content="{esc(desc)}">',
        f'<link rel="canonical" href="{esc(url)}">',
        f'<meta property="og:type" content="{"article" if kind == "lesson" else "website"}">',
        f'<meta property="og:site_name" content="{esc(site["title"])}">',
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(desc)}">',
        f'<meta property="og:url" content="{esc(url)}">',
        f'<meta property="og:image" content="{esc(image)}">',
        '<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">',
        '<meta property="og:image:alt" content="A red Northern line train leaving a round tunnel, above the title Commute Algorithms.">',
        '<meta name="twitter:card" content="summary_large_image">',
    ]
    if kind == "all":
        tags.append('<meta name="robots" content="noindex">')  # duplicate of the lesson pages
    return "\n".join(tags)


def build():
    cur = json.loads((ROOT / "curriculum.json").read_text())
    validate(cur)
    stage_title = {s["id"]: s["title"] for s in cur["stages"]}
    by_id = {l["id"]: l for l in cur["lessons"]}
    LESSON_IDS.update(by_id)
    written = {l["id"] for l in cur["lessons"] if (LESSONS / f"{l['id']}.html").exists()}
    for f in LESSONS.glob("*.html"):
        if f.stem not in by_id:
            raise BuildError(f"{f.name} is not listed in curriculum.json")

    diagrams = Diagrams()
    order = cur["lessons"]
    done = [l for l in order if l["id"] in written]
    parts, all_problems, lesson_problems, home_of_problem = {}, [], {}, {}
    for l in done:
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
        lesson_problems[l["id"]] = problems
        for p in problems:
            home_of_problem.setdefault(p, l["id"])
        parts[l["id"]] = (body, answers)

    dupes = {p for p in all_problems if all_problems.count(p) > 1}
    if dupes:
        print(f"note: problems used in more than one lesson: {', '.join(sorted(dupes))}")

    def article(l, mode):
        """mode 'page': standalone lesson page in l/. mode 'all': inside all.html."""
        i = order.index(l)
        body, answers = parts[l["id"]]
        problems = lesson_problems[l["id"]]
        href = (lambda x: f"{x}.html") if mode == "page" else (lambda x: f"#{x}")
        if mode == "page":
            fix = link_rewriter(home_of_problem, l["id"])
            body, answers = fix(body), fix(answers)
        reqs = ", ".join(f'<a href="{href(r)}">{esc(by_id[r]["title"])}</a>' for r in l["requires"])
        meta = [esc(stage_title[l["stage"]])]
        if problems:
            meta.append(f'<span class="lesson-progress" data-lesson="{l["id"]}">{len(problems)} problem{"s" if len(problems) != 1 else ""}</span>')
        head = (
            f'<header class="lesson-head"><p class="kicker">Lesson {i} &middot; {" &middot; ".join(meta)}</p>'
            f'<h2>{esc(l["title"])}</h2>'
            + (f'<p class="requires">Read first: {reqs}</p>' if reqs else "")
        )
        if mode == "page":
            head += '<button type="button" class="print-btn" data-print="page">Print this lesson / Save as PDF</button>'
        head += "</header>"
        return (f'<article id="{l["id"]}" data-problems="{" ".join(problems)}">'
                f"{head}{body}{answers}</article>")

    def pager(l):
        k = done.index(l)
        prev = done[k - 1] if k else None
        nxt = done[k + 1] if k + 1 < len(done) else None
        cell = lambda x, cls, label: (
            f'<a class="{cls}" href="{x["id"]}.html"><small>{label}</small>{esc(x["title"])}</a>' if x else "<span></span>")
        return (f'<nav class="pager no-print">{cell(prev, "prev", "&larr; Previous")}'
                f'{cell(nxt, "next", "Next &rarr;")}</nav>')

    # Home page: photo, progress, stage list (each stage is a <details>).
    toc = []
    for s in cur["stages"]:
        items, n_written = [], 0
        for i, l in enumerate(order):
            if l["stage"] != s["id"]:
                continue
            if l["id"] in written:
                n_written += 1
                items.append(f'<li><a href="l/{l["id"]}.html"><span class="num">{i}</span> {esc(l["title"])}</a>'
                             f' <span class="toc-progress" data-lesson="{l["id"]}"></span></li>')
            else:
                items.append(f'<li class="soon"><span class="num">{i}</span> {esc(l["title"])} <small>(coming soon)</small></li>')
        status = f'{n_written} lesson{"s" if n_written != 1 else ""}' if n_written else "coming soon"
        toc.append(f'<details class="stage" open data-stage="{s["id"]}"><summary>{esc(s["title"])}'
                   f' <small class="stage-status">{status}</small></summary><ul>{"".join(items)}</ul></details>')
    diagrams.prune()

    shell = (ROOT / "template.html").read_text()
    common = {
        "{{TITLE}}": esc(cur["title"]),
        "{{TAGLINE}}": esc(cur["tagline"]),
        "{{CODE_CSS}}": (TOOLS / "code.css").read_text(),
        "{{UPDATED}}": date.today().isoformat(),
        "{{REPO}}": esc(cur["repo"]),
        "{{DATA}}": json.dumps({
            "lessons": {k: lesson_problems[k] for k in lesson_problems},
            "titles": {l["id"]: l["title"] for l in done},
            "pages": [f"l/{l['id']}.html" for l in done],
            "stages": [{"title": s["title"], "lessons": [l["id"] for l in done if l["stage"] == s["id"] and lesson_problems[l["id"]]]}
                       for s in cur["stages"]],
            "assets": sorted(f"diagrams/{n}" for n in diagrams.used) + ["images/tube.webp"],
        }, separators=(",", ":")),
    }

    def page(path, kind, title, root, body, desc, share_title=None):
        url = cur["url"] + ("" if path == "index.html" else path)
        head = head_tags(cur, url, html.unescape(share_title or title), desc, kind)
        out = shell
        for k, v in {**common, "{{PAGE_TITLE}}": title, "{{KIND}}": kind, "{{ROOT}}": root,
                     "{{HEAD}}": head, "{{BODY}}": body}.items():
            out = out.replace(k, v)
        if root:  # pages in l/ reach diagrams one level up
            out = out.replace('="diagrams/', f'="{root}diagrams/')
        (ROOT / path).parent.mkdir(exist_ok=True)
        (ROOT / path).write_text(out)
        return len(out)

    total = len(set(all_problems))
    home = (
        f'<header class="site-head"><h1>{esc(cur["title"])}</h1>{HERO}<p class="lead">{esc(cur["tagline"])}</p>'
        f'<p class="progress-line no-print">Solved: <span id="solved-count">0</span> / {total} problems</p>'
        f'<p id="resume" class="resume no-print" hidden></p></header>'
        f'<section id="map"><h2>Lessons</h2>'
        f'<p class="muted">Go from top to bottom. Each stage builds on the one above it. Tap a stage to open it.</p>'
        f'<div class="toc">{"".join(toc)}</div>'
        f'<p class="no-print"><a href="all.html">Print the whole guide</a> (one big page, for printing only)</p>'
        f"</section>"
    )
    sizes = {"index.html": page("index.html", "home", esc(cur["title"]), "", home, cur["tagline"])}

    if PAGES.exists():
        for f in PAGES.glob("*.html"):
            if f.stem not in written:
                f.unlink()
    for l in done:
        k = done.index(l)
        nxt = f'<a href="{done[k + 1]["id"]}.html">Next &rarr;</a>' if k + 1 < len(done) else ""
        top = f'<nav class="topbar no-print"><a href="../">&larr; All lessons</a>{nxt}</nav>'
        share = ('<p class="share no-print" hidden><button type="button" class="share-btn">'
                 'Send this lesson to a friend</button></p>')
        desc = first_text((LESSONS / f"{l['id']}.html").read_text()) or cur["tagline"]
        sizes[f"l/{l['id']}.html"] = page(
            f"l/{l['id']}.html", "lesson", f'{esc(l["title"])} &middot; {esc(cur["title"])}', "../",
            top + article(l, "page") + share + pager(l), desc, f'{l["title"]}: {cur["title"]}')

    every = "".join(article(l, "all") for l in done)
    intro = (f'<header class="site-head no-print"><p><a href="./">&larr; Back to lessons</a></p>'
             f'<h1>{esc(cur["title"])}: the whole guide</h1><p class="muted">Every lesson on one page, for printing.</p>'
             f'<button type="button" class="print-btn" data-print="page">Print the whole guide</button></header>')
    sizes["all.html"] = page("all.html", "all", f'{esc(cur["title"])}: whole guide', "", intro + every,
                             "Every lesson of " + cur["title"] + " on one page, for printing.")

    # For search engines and "Add to Home Screen".
    urls = [(cur["url"], max(git_date(LESSONS / f"{l['id']}.html") for l in done))]
    urls += [(cur["url"] + f"l/{l['id']}.html", git_date(LESSONS / f"{l['id']}.html")) for l in done]
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{esc(u)}</loc><lastmod>{d}</lastmod></url>\n" for u, d in urls)
        + "</urlset>\n")
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {cur['url']}sitemap.xml\n")
    (ROOT / "manifest.webmanifest").write_text(json.dumps({
        "name": cur["title"],
        "short_name": "Commute Algo",
        "description": cur["tagline"],
        "start_url": "./",
        "scope": "./",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#ffffff",
        "icons": [
            {"src": "images/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "images/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ],
    }, indent=2) + "\n")

    lesson_sizes = [v for k, v in sizes.items() if k.startswith("l/")]
    print(
        f"built {len(sizes)} pages: {len(written)}/{len(order)} lessons, {total} problems, "
        f"{len(diagrams.used)} diagrams ({diagrams.rendered} newly rendered). "
        f"index {sizes['index.html'] // 1024} KB, lessons {min(lesson_sizes) // 1024}-{max(lesson_sizes) // 1024} KB, "
        f"all.html {sizes['all.html'] // 1024} KB"
    )


if __name__ == "__main__":
    try:
        build()
    except BuildError as e:
        sys.exit(f"build failed: {e}")
