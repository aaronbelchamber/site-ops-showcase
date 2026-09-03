# Mission

Note: this folder is named `site-ops-showcase` locally, but the actual GitHub
repo is `aaronbelchamber/site-ops` (no `-public` suffix) -- use that name for
`gh`/API calls, issues, or links.

WordPress Site Manager is a local-first dashboard and CLI for managing a
fleet of WordPress sites (remote over SSH, or local) from one place. It
covers health checks (HTTP/WP API status, screenshot diffing, console-error
capture via a headless browser), a transactional update engine (pre-update
health check, DB and file backup, apply, post-update verification, and
auto-rollback on failure), WP-CLI vulnerability scanning, encrypted-at-rest
credential storage (AES-256 Fernet), reusable SSH login profiles so a site
doesn't need its credentials re-entered by hand (`src/api/routes/profiles.py`,
surfaced as "Shared Login Profile" in `AddSiteForm.jsx`), and automated
Google Drive sync of config backups. The backend is Flask
(`src/api/routes/`: health, updates, backups, sites, system, profiles); the
frontend is a React/Vite SPA.

Login profiles shipped smaller than originally designed: [`settings_plan.md`](settings_plan.md)
proposed a richer system -- named infra-type presets (`aws-lightsail`,
`kinsta`, etc. with their own `wp_path`/`wp_cli_path` defaults), domain-match
auto-fill rules, and JSON import/export. What actually shipped only reuses
SSH credentials (host/port/user/key), manually named and applied -- no
presets, no domain rules, no import/export. Not wrong, just smaller; the
richer design in that doc is still there if it's ever worth revisiting.

## What this is for

A public, standalone demonstration of infrastructure tooling: a
transactional update engine with automatic rollback, encrypted-at-rest
credential storage instead of plaintext config, and a clean separation
between an orchestration backend and a dashboard UI. It's a real working
tool, not a stripped-down demo -- it manages Aaron's own sites too, alongside
the canonical private repo.

## Who it's for

Anyone evaluating this as a portfolio piece or wanting a self-hosted,
single-operator WordPress fleet manager they can run themselves. Not built
for a team or multi-tenant SaaS use -- single operator, local-first, no
external service dependency beyond WP-CLI/SSH and optional Google Drive
backup sync.

## What it is not

- Not a content or marketing tool -- it does not touch WordPress content,
  posts, or SEO. It manages the infrastructure a WordPress install runs on
  (updates, backups, health, security scanning), not what's published on it.
- Not a hosting platform or WordPress installer -- it manages sites that
  already exist.
- Not multi-tenant or subscription software -- no accounts, no billing, no
  cloud-hosted backend.
- Not the source of truth for ongoing development -- see below.

## Related projects -- and, if applicable, how they work together

- **site-ops** (private repo, canonical upstream).
  This repo is the synced public release of that project -- development
  happens there first and is synced out here (sync direction is private ->
  public, one way; this repo has no dependency back on the private one, it's
  a full working copy). The private repo currently has features this one
  doesn't yet (WP-CLI vulnerability scanning as a full endpoint, WordPress
  user management) -- confirmed by comparing `src/api/routes/` between the
  two repos.
  **Drift risk, confirmed real**: both repos independently modified
  `HealthCheckDetails.jsx` within the same week -- this repo added a
  Production Health dashboard on 2026-08-22 (commit `52ef703`) while the
  private repo refactored the same component into a directory split on
  2026-08-25. This repo still has the pre-split single file, so the two have
  already diverged on a shared UI component. Shared-component changes should
  be made once in the private repo and synced out here, not made
  independently in both.
