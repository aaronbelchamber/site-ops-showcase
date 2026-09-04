> **Standing preferences apply to this repo.** The operator of this project
> keeps them outside this repository, in four cross-project files —
> `PREFERENCES.md` (ports, launching processes without a window, URL hygiene,
> hosting), `PRACTICES.md` (script placement, file size, verification, design
> systems, self-review, CI), `COLLABORATION.md` (version control and branch
> conventions, worktrees rather than `main`) and `DOCUMENTATION.md` (writing a
> doc in the tense of what exists, session retros). All four are canonical
> where they and anything below disagree.
>
> They are not published here, and they are not something an outside
> contributor needs: everything required to build, test and run this project is
> in this repo. If you are working with the drive mounted they are in
> `E:\project-hub\` — read all four before changing anything.

# AGENTS.md

Read MISSION.md for what this is.

## Repo name

The local folder is `site-ops-showcase` and so is the GitHub repo:
`aaronbelchamber/site-ops-showcase`. They match -- use that name for any `gh`
command, API call, issue link or clone URL.

This section said the opposite until 2026-09-04: that the real repo was
`aaronbelchamber/site-ops`, and to use *that* name for every `gh` command. That
is the **private** upstream, a different repository, and following it pointed
public-repo work at a repo outside contributors cannot even read. It came in
with `4258044 Collapse the site-ops pair to a single repository`, whose premise
did not hold -- the pair was never collapsed. `MISSION.md` was corrected in
`c2ca2b0` and this file was missed. Verified against `git remote -v` in both
trees on 2026-09-04.

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
