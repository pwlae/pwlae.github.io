# Commute Algorithms (pwlae.github.io)

A single, long web page that teaches algorithms step by step, from zero, for people
who study on their phone during a 30–60 minute commute (the owner rides the London
Underground: Northern line, then Jubilee line). Hosted on GitHub Pages from `master`.

## Why it exists (the owner's brief, condensed)

- Opening random LeetCode problems on the train is unstructured, and no progress follows.
  Structured, aggressive prep (e.g. before an interview) works. This site gives the
  commute that structure.
- A friend's advice: start with the easiest problems, solve **lots** of them **quickly**,
  and step up difficulty only once easy ones feel fast. Never sit on one problem for days.
  (The owner once lost 3 days of commutes to one unsolved medium. The train ends,
  context is lost, and the next ride starts from scratch.)
- Each lesson: short, very simple theory → Python example → links to LeetCode problems,
  easiest first. Goal: the reader feels progress and learns all the main algorithms,
  not to become a competitive programmer.
- **Written for absolute beginners.** No walls of text. If a topic needs earlier topics,
  link to them, but still keep it as simple as possible.

## Hard requirements

- **Light and fast.** Poor signal underground. Minimal CSS, inline CSS/JS, no frameworks,
  no web fonts, no runtime JS libraries. Current page ≈ 50 KB, so keep it lean.
- **Phone first.** 16px side gutter, big tap targets, no horizontal page scroll.
- **Printable.** White background, no coloured backgrounds, black text. Every lesson has an
  explicit "Print this lesson / Save as PDF" button. On print: hints/facts expand, LeetCode
  URLs are printed, solutions move to an "Answers" page at the end of the lesson.
- **Python only** for now, with syntax highlighting (Pygments at build time). Don't hard-code
  Python assumptions: the code pipeline takes any Pygments language, so other languages can come later.
- **Diagrams: Mermaid only.** Nothing else (no hand-drawn SVG, no images, no ASCII art).
  They are rendered to SVG at build time (`diagrams/<hash>.svg`), so readers don't download Mermaid.
- **LeetCode links are explicit**: the card shows the LeetCode logo, a "LeetCode" label,
  number, title, difficulty and time box. Link is `https://leetcode.com/problems/<slug>/`
  (phones with the LeetCode app may open it there).
- **"Interesting fact"** expandable on every lesson: how this algorithm or data structure is
  used in a well-known real system (Git, Linux, databases, browsers, Google Maps…).
  Facts must be true. Prefer well-documented ones and avoid made-up specifics.
- Progress ("Solved" ticks, last lesson read) lives in `localStorage` only. No accounts, no backend.
- Works offline after one visit (`sw.js`).

## How the site is built

```
curriculum.json      stages + ordered lessons (id, title, stage, requires) ← source of truth
lessons/<id>.html    one HTML fragment per lesson (no <html>/<body>)
template.html        page shell: all CSS + JS inline
tools/code.css       highlight colours   tools/mermaid.json   diagram theme
build.py             → index.html (GENERATED, committed) + diagrams/*.svg
sw.js                offline cache
```

- Build: `python3 build.py` (needs `pygments`. First time: `PUPPETEER_SKIP_DOWNLOAD=1 npm install`,
  which uses the system Chromium at /snap/bin/chromium).
- Check problems: `python3 tools/check_problems.py <lesson-id>` (verifies slug, number, title,
  difficulty and not-premium against LeetCode's API).
- Lessons not yet written still show in the map as "coming soon". Lessons may be written in any
  order, but the map and numbering follow `curriculum.json`.
- Preview: `python3 -m http.server 8765`, then
  `/snap/bin/chromium --headless --no-sandbox --hide-scrollbars --window-size=390,6000 --screenshot=$PWD/preview/m.png http://localhost:8765/#<id>`
  and `--print-to-pdf=$PWD/preview/<id>.pdf "http://localhost:8765/?print=<id>"`. Use `preview/`
  (gitignored), because snap Chromium cannot write to /tmp. Look at both before finishing a lesson.

## Writing a lesson (the format every lesson follows)

Target: **~10 minutes of reading + 3–6 problems ≈ one commute.** Roughly 400–900 words of
prose, not counting code. Short sentences. Plain words. Define every term the first time.

Sections, in this order (use `<h3>`):

1. `<p class="lead">`: one or two sentences: what this is and why you'd want it.
2. **The idea**: a real-life picture (queue at a shop, stack of plates…), then how it works
   in a few steps. At least one Mermaid diagram.
3. **In Python**: the reusable code template with comments, and its time/space cost in words
   ("one pass over the list: O(n)") once Big O has been taught.
4. **Worked example**: optional. Walk through one tiny input step by step (a table works well).
5. **Your turn**: 3–6 `<leetcode>` cards, **easiest first**, each with `minutes` (time box),
   a `<hint>` that nudges without giving it away, and a full `<solution>` (Python, commented,
   LeetCode's exact method signature). Mostly Easy problems. A Medium only near the end,
   marked as a stretch. Each problem should be used in only one lesson.
6. `<fact title="...">`: the interesting real-world use.
7. `<recap>`: a 3-bullet "Remember" list (what you'd want on a flashcard).

Markup available in lesson files (build.py expands it):

```html
<pre><code class="language-python">...</code></pre>          <!-- highlighted code; escape < as &lt; is optional -->
<pre class="mermaid" data-alt="what the diagram shows">flowchart LR ...</pre>  <!-- data-alt required -->
<leetcode slug="two-sum" num="1" title="Two Sum" level="Easy" minutes="10">
  <hint>...</hint>
  <solution><pre><code class="language-python">...</code></pre></solution>
</leetcode>
<fact title="Short title">...</fact>
<recap><ul><li>...</li></ul></recap>
```

Mermaid tips: keep diagrams narrow (`flowchart TD` or short `LR` rows) so they read on a
phone. Labels are plain text (`<br/>` for line breaks; no `<b>`). Theme is Mermaid's standard "default" theme.
Supported: flowchart, sequence, state, class, etc.

Look at `lessons/python-toolkit.html` as the model lesson.

## Loop workflow (Linear)

Work is tracked in Linear: workspace **pwlae-personal-blog**, team **PWL**, project
**algorithmic-coding-easy**. One issue per lesson. The issue description lists the scope,
the verified problem set, a diagram idea and a fact idea. Issues are linked with
"blocked by" relations that follow the curriculum order. Lesson N (its position in
`curriculum.json`, counting from 0) is issue **PWL-(N+6)**: lesson 2 Big O = PWL-8 … lesson 30 Trie = PWL-36.
PWL-5 is the scaffold.

Each loop iteration:
1. List the project's issues and pick the **lowest-numbered issue not Done** whose
   blockers are all Done. Move it to **In Progress**.
2. Write `lessons/<id>.html` following the format above and the issue's notes. You may swap
   a problem if it fits the lesson better: verify it with `tools/check_problems.py`.
3. `python3 tools/check_problems.py <id>` and `python3 build.py` must both pass. Look at the
   phone screenshot and the `?print=<id>` PDF.
4. Commit (`Add lesson: <title> (PWL-N)`) and push to `master`. Pushing deploys the site.
5. Comment on the issue with a short summary (problems used, anything changed) and move it to **Done**.
6. One lesson per iteration. If something in the site itself needs fixing, open a new
   issue in the same project instead of mixing it into a lesson commit.
