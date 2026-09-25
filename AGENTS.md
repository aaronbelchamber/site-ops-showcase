> **Standing preferences apply to this repo.** The operator of this project
> keeps them outside this repository, in a set of cross-project files that are
> canonical wherever they and anything below disagree. They are not published
> here, and an outside contributor does not need them. With the drive mounted
> they are in `E:\project-hub\docs\standards\` — list `*.md` there and read what
> is present rather than trusting a list written here.

# AGENTS.md

Read MISSION.md for what this is.

## This repo is archived -- read it, do not work in it

`origin` here is `aaronbelchamber/site-ops-showcase`, which is public and
**archived**. GitHub refuses every push to it:

```
ERROR: This repository was archived so it is read-only.
```

Every commit made here is pushed, so this tree matches `origin/main`, and the
folder sits under `projects\archives\`. Active development is in the
**private** `aaronbelchamber/site-ops`, a separate repository, not a rename.
Take any change, issue or `gh` command there instead.

`git remote -v` only prints a configured string; `gh repo view <name> --json
isArchived,visibility` is what says whether the other end accepts writes.

| Repo | Visibility | State |
|---|---|---|
| `aaronbelchamber/site-ops-showcase` | public | archived, read-only |
| `aaronbelchamber/site-ops` | private | active |

## Running locally

The estate's port registry no longer reserves these ports for this archive, so
another project may hold them; check before starting it.

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
- **CI no longer runs anywhere for this code.** `.github/workflows/ci.yml` was
  the coverage for both repos while this public half accepted pushes; since the
  archive nothing triggers it. `site-ops` is covered by a local pre-merge test
  gate instead, ruled 2026-09-14 — see that repo's AGENTS.md.

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
