# Personal Workbench Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task. Steps use checkbox syntax.

**Goal:** Build and push a Chinese single-user workbench, then verify and save its cloud setup.
**Architecture:** Flask JSON API, SQLite persistence, same-origin responsive HTML/CSS/JS.
**Tech Stack:** Python 3.12+, Flask 3.1.2, Waitress 3.0.2; unittest and Playwright.
**Spec:** ../specs/2026-10-25-workbench-design.md

## Global Constraints

- No credentials, user data or generated dependencies committed.
- Use the existing isolated checkout; no extra worktree.
- Local validation is distinct from public deployment.

## Review Focus

- Unauthorized access must not expose records or backups.
- Invalid links and dates must be rejected without losing data.
- Stale edits from another device must return a conflict.
- Restart must preserve data and signing material.
- Narrow screens and untrusted HTML must remain usable and safe.

### Task 1: API and persistence

Files: `app.py`, `storage.py`, `tests/test_app.py`, `requirements.txt`.
Interfaces: `create_app(data_dir, password=None)` returns Flask app; JSON routes
`/api/session`, `/api/login`, `/api/logout`, `/api/entries`, `/api/entries/<id>`, `/api/export`.

- [ ] Write behavioral API tests for authentication, CRUD, validation, conflicts, persistence and export.
- [ ] Run `python -m unittest discover -s tests -v`; observe missing implementation.
- [ ] Implement API, private state directory and SQLite versioned updates.
- [ ] Run the suite; require all tests passing.

### Task 2: Responsive interface

Files: `templates/index.html`, `static/app.js`, `static/style.css`, `tests/browser_smoke.py`.
Consumes Task 1 JSON routes; produces a Chinese login and workbench.

- [ ] Write browser checks for real login, task completion, notes, links, reload persistence and mobile layout.
- [ ] Run against the service and observe missing interface.
- [ ] Implement accessible forms, text-safe rendering, search, polling, version conflict handling and export.
- [ ] Run browser checks at desktop and 390px mobile widths.

### Task 3: Delivery and environment

Files: `README.md`, `.github/workflows/test.yml`, `scripts/check.sh`.

- [ ] Document installation, password management, persistent data, HTTPS deployment and backup.
- [ ] Exercise installation, startup, restart and live authenticated HTTP request.
- [ ] Review code, run required checks, commit and push `HEAD:main` without force.
- [ ] Save tested install/start configuration; verify remote commit and clean repository state.
