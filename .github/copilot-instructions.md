# Copilot instructions

Read MISSION.md for what this is.

## Repo name mismatch

The local folder is `wordpress-site-manager-public`, but the GitHub repo is
`aaronbelchamber/wordpress-site-manager` (no `-public` suffix). Use that name
in any `gh`/API call, issue link, or clone URL suggestion.

## Running locally

- Backend: `python manage.py init` once, then `python manage.py runserver`
  (Flask, port 5000).
- `run_dev.bat`: dependency check/install, bootstraps `config/.env` and
  `frontend/.env.local`, `npm install` if needed, launches backend + Vite
  dev server (5173, `/api` proxied to 5000).
- `run.bat`: builds the frontend then runs Flask without debug/auto-reload.
- Frontend (`frontend/`): `npm run dev` / `npm run build` / `npm run lint`
  (oxlint) / `npm run test` (vitest).
- Backend tests: `pytest` from repo root.
- No `requirements.txt` is committed; the batch launchers pip-install
  dependencies directly. No CI workflow exists here.

## Sync direction and drift risk

This repo is a synced-out public release. Development happens first in
**wordpress-site-manager-private**, then syncs out here — one-way, private
to public, with no dependency back on the private repo. Independently
editing shared components in this repo risks drift: both repos modified
`HealthCheckDetails.jsx` in the same week (this repo added a Production
Health dashboard, the private repo split it into a directory), and the two
are now out of sync. When suggesting changes to shared backend/UI logic,
prefer noting they should originate in wordpress-site-manager-private and
sync out, rather than editing independently here.

## What this is / isn't

A public, standalone demonstration of infrastructure tooling — a real
working tool, not a stripped-down demo, with no dependency on any other
project. Not the source of truth for ongoing development; see MISSION.md's
Related projects section.
