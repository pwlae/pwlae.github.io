---
description: One iteration of the parallel lesson loop. Run with `/loop /lesson-loop`.
---

You are the **orchestrator** of the lesson loop for this repo. Follow CLAUDE.md
("Loop workflow (Linear, parallel)") and the steps below. The owner has approved:
spawning subagents, working in git worktrees, and merging + pushing to `master`
without review.

## 1. Find the work

- Make sure the main checkout is on `master`, clean, and up to date (`git pull --ff-only`).
  If it isn't clean, stop and tell the owner. Don't discard anything.
- List every issue in Linear project **algorithmic-coding-easy** (team PWL) that is not
  Done or Canceled, with its blocked-by relations.
- **Leftovers first:** an issue that is In Progress but whose work is already on `master`
  (e.g. `lessons/<id>.html` committed with `(PWL-N)` in the message) only needs its
  summary comment and a move to Done. Do that yourself, no subagent.
- **Ready** = not Done, and every blocker is Done. If nothing is ready and nothing is
  left, the project is finished: say so and stop the loop. If nothing is ready but
  issues remain, report what blocks them and stop the loop. That needs the owner.

## 2. Fan out: one subagent per ready issue

For each ready issue, all in one message so they run in parallel:
- Move it to **In Progress** in Linear.
- Spawn an Agent with `isolation: "worktree"`, giving it the subagent brief below
  with `<PWL-N>`, `<id>` (lesson id from curriculum.json) and the issue description
  filled in.

Then wait for all of them to finish. Don't poll. You'll be notified.

### Subagent brief (paste and fill in)

> You are writing **<PWL-N>** in a git worktree of the Commute Algorithms repo.
> Read CLAUDE.md first, then follow "Writing a lesson" exactly and use
> `lessons/python-toolkit.html` as the model. The Linear issue says:
>
> <issue description>
>
> Setup (the worktree has no node_modules or preview folder):
> `ln -s <main checkout>/node_modules node_modules && mkdir -p preview`
>
> Rules:
> - Write only `lessons/<id>.html`. If the issue isn't a lesson, change only the
>   files it needs. Don't edit curriculum.json, template.html or build.py unless the
>   issue is about them.
> - Problems: `python3 tools/check_problems.py <id>` must pass. Each problem may be
>   used in only one lesson: `grep -l 'slug="<slug>"' lessons/*.html` must show only
>   your file. You may swap a problem for a better fit if it passes the checker.
> - `python3 build.py` must pass. Preview on port **8700 + N** (PWL-33 → 8733) with
>   `python3 -m http.server <port>`. Look at a 390px phone screenshot of
>   `l/<id>.html` and its printed PDF (see CLAUDE.md "Preview"). Diagrams ≤ 450px wide.
> - Commit on your worktree branch **only** `lessons/<id>.html` and any new
>   `diagrams/*.svg` it uses: `git add lessons/<id>.html diagrams/` (never `git add -A`;
>   don't commit index.html, all.html, l/, sitemap.xml or the node_modules link).
>   Message: `Add lesson: <title> (<PWL-N>)`.
> - Do **not** push, merge, or change anything in Linear. The orchestrator does that.
> - Reply with: branch name, commit SHA, problems used (num, slug, level), anything
>   you changed from the issue's plan, and any problem you noticed in the site itself.

## 3. Merge, one at a time, in curriculum order

For each subagent that reported success:
1. `git merge --squash <branch>`, then `python3 build.py` and
   `python3 tools/check_problems.py <id>`. Both must pass.
2. `git add -A` and commit `Add lesson: <title> (<PWL-N>)` with the co-author line.
   The generated pages are rebuilt here, so parallel branches never clash on them.
3. `git push origin master`.
4. Comment on the Linear issue: problems used, anything changed from the plan.
   Move it to **Done**.
5. Remove the worktree and delete its branch.

If a merge or build fails: `git reset --hard origin/master` (only your own
uncommitted merge is lost). Then fix it yourself if it's small, or send the error back
to that subagent. Never push a failing build. If a subagent failed or gave up, leave its
issue In Progress, comment on what went wrong, and carry on with the others.

Site problems a subagent noticed go into **new** Linear issues in the same project
(with sensible blocked-by relations), not into lesson commits.

## 4. Report and continue

Report in a few lines: lessons merged, issues Done, anything stuck. Then let the loop
continue. The next iteration picks up anything newly unblocked.
