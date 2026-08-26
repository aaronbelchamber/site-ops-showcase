# CLAUDE.md

Read MISSION.md for what this is.

## Repo name mismatch

The local folder is `wordpress-site-manager-public`, but the actual GitHub
repo is `aaronbelchamber/wordpress-site-manager` (no `-public` suffix). Use
that name for any `gh` command, API call, issue link, or clone URL.

## Running locally

- Backend: `python manage.py init` once, then `python manage.py runserver`
  (Flask, port 5000). `run_dev.bat` does dependency checks, `.env`/
  `frontend/.env.local` bootstrapping, `npm install`, and launches backend +
  Vite dev server (port 5173, proxies `/api` to 5000) together. `run.bat` is
  the production-style path: builds the frontend then runs Flask without
  debug/auto-reload.
- Frontend (`frontend/`): `npm run dev` / `npm run build` / `npm run lint`
  (oxlint) / `npm run test` (vitest).
- Backend tests: `pytest` from the repo root (`tests/`).
- No `requirements.txt` is committed here; `run_dev.bat`/`run.bat` pip-install
  the needed packages directly (flask, python-dotenv, paramiko, pyyaml,
  cryptography, requests). No CI workflow exists in this repo.

## Sync direction and drift risk

This repo is a synced-out public release. Development happens in
**wordpress-site-manager-private** first, then syncs out here — one way,
private to public. This repo has no dependency back on the private one, but
edits to shared components made independently here can and have drifted from
the private repo (see MISSION.md's `HealthCheckDetails.jsx` example: both
repos modified the same component the same week and are now out of sync).
If a change touches shared backend/UI logic, it should ideally originate in
wordpress-site-manager-private and sync out here, not be made independently
in this repo.

## What this is / isn't

Public demonstration of the infrastructure tooling — a real, working tool
(it manages Aaron's own sites too), not a stripped-down demo, and standalone
with no dependency on any other project. It is not the source of truth for
ongoing development of this project; see MISSION.md's Related projects
section for the fuller picture.
