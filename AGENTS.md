> **Standing preferences apply to this repo.** The operator of this project
> keeps them outside this repository, in a set of cross-project files —
> `PREFERENCES.md` (ports, launching processes without a window, URL hygiene,
> hosting), `PRACTICES.md` (script placement, file size, design systems, who
> owns what across projects), `VERIFICATION.md` (how a claim that work is
> finished gets established, self-review, CI), `COLLABORATION.md` (version
> control and branch conventions, worktrees rather than `main`) and
> `DOCUMENTATION.md` (writing a doc in the tense of what exists, session
> retros). All of them are canonical where they and anything below disagree.
>
> They are not published here, and they are not something an outside
> contributor needs: everything required to build, test and run this project is
> in this repo. If you are working with the drive mounted they are in
> `E:\project-hub\` — list `*.md` there and read what is present before
> changing anything, rather than working from the list above: the set grows
> each time one of those files outgrows its own size rule.

# AGENTS.md

Read MISSION.md for what this is.

## This repo is archived -- read it, do not work in it

`origin` here is `aaronbelchamber/site-ops-showcase`, which is public and
**archived**. GitHub refuses every push to it:

```
ERROR: This repository was archived so it is read-only.
```

So this working tree is a historical copy. A commit made here can be made, and
can never be published. Active development is in the **private**
`aaronbelchamber/site-ops` -- a genuinely separate repository, not a rename --
which is what `4258044 Collapse the site-ops pair to a single repository`
recorded. Take any change to that repo instead.

Two earlier attempts to write this section down were each half right, and the
way they failed is the useful part. The original said the folder "is really"
`aaronbelchamber/site-ops` and to use that name for every `gh` command: right
about where work goes, wrong that this tree is that repo -- following it files
issues against a repository this checkout is not. `c2ca2b0` and then this file
on 2026-09-04 corrected it the other way, to "the names match, use
site-ops-showcase", on the strength of `git remote -v` agreeing in both trees.

`git remote -v` prints a configured string. It says nothing about whether the
repository on the other end exists, accepts writes, or is still the one anyone
uses -- and here it was pointing at an archive. `gh repo view <name> --json
name,visibility` and an actual push are what answer that; the archive only
surfaced when a push was attempted. State verified on 2026-09-04:

| Repo | Visibility | State |
|---|---|---|
| `aaronbelchamber/site-ops-showcase` | public | archived, read-only |
| `aaronbelchamber/site-ops` | private | active |

## Running locally

- Backend: `python manage.py init` once, then `python manage.py runserver`
  (Flask, port 63010).
- `run_dev.bat`: checks/installs Python deps, bootstraps `config/.env` and
  `frontend/.env.local`, runs `npm install` if needed, and starts backend +
  Vite dev server (63014, `/api` proxied to 63010) in separate windows.
- `run.bat`: production-style — builds the frontend (`npm run build`) then
  runs Flask with `--no-debug`.
- Frontend commands (run inside `frontend/`): `npm run dev`, `npm run build`,
  `npm run lint` (oxlint), `npm run test` (vitest).
- Backend tests: `pytest` from repo root (`tests/`).
- Dependencies are declared in `requirements.txt` (runtime) and
  `requirements-dev.txt` (adds pytest). The batch launchers used to be the only
  record of them and had fallen behind the code -- Pillow, playwright, pydantic,
  waitress and werkzeug are all imported and none were in that list.
- **CI runs here**, in `.github/workflows/ci.yml`: pytest on Python 3.11 and
  3.12, plus lint, tests and build for the frontend. This is the public half of
  the pair, so Actions minutes are free, and this run is the coverage for both
  repos -- `site-ops` deliberately has no automatic suite
  of its own.

## Sync direction and drift risk

This is a synced-out public release, not the canonical repo. Development
happens in **site-ops** first and is synced out here
(private -> public, one-way). This repo has no dependency back on the
private one — it's a full working copy — but independent edits to shared
components here risk diverging from the private repo. Confirmed real case:
both repos modified `HealthCheckDetails.jsx` in the same week (this repo
added a Production Health dashboard; the private repo refactored the same
component into a directory split), and the two versions are now different.
Prefer making shared backend/UI logic changes in site-ops
and syncing them out, rather than changing them here independently.

## What this is / isn't

A public, standalone demonstration of infrastructure tooling — a real
working tool (also manages Aaron's own sites), not a stripped-down demo, and
with no dependency on any other project. Not the source of truth for ongoing
development — see MISSION.md's Related projects section for details.
