> **Standing preferences apply to this repo.** The operator of this project
> keeps one cross-project preferences file — ports, launching processes without
> a window, URL hygiene, branch conventions, script placement, file-size
> thresholds, verification, design systems, self-review — outside this
> repository, and it is canonical where it and anything below disagree.
>
> It is not published here, and it is not something an outside contributor
> needs: everything required to build, test and run this project is in this
> repo. If you are working with the drive mounted, read it before changing
> anything.

# AGENTS.md

Read MISSION.md for what this is.

## Repo name mismatch

The local folder is `wordpress-site-manager-public`, but the actual GitHub
repo is `aaronbelchamber/wordpress-site-manager` (no `-public` suffix). Use
that name for any `gh` command, API call, issue link, or clone URL — the
folder name will not match.

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
  repos -- `wordpress-site-manager-private` deliberately has no automatic suite
  of its own.

## Sync direction and drift risk

This is a synced-out public release, not the canonical repo. Development
happens in **wordpress-site-manager-private** first and is synced out here
(private -> public, one-way). This repo has no dependency back on the
private one — it's a full working copy — but independent edits to shared
components here risk diverging from the private repo. Confirmed real case:
both repos modified `HealthCheckDetails.jsx` in the same week (this repo
added a Production Health dashboard; the private repo refactored the same
component into a directory split), and the two versions are now different.
Prefer making shared backend/UI logic changes in wordpress-site-manager-private
and syncing them out, rather than changing them here independently.

## What this is / isn't

A public, standalone demonstration of infrastructure tooling — a real
working tool (also manages Aaron's own sites), not a stripped-down demo, and
with no dependency on any other project. Not the source of truth for ongoing
development — see MISSION.md's Related projects section for details.
