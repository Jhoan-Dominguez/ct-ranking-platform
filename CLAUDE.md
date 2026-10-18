# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

CT Ranking is a Streamlit platform for university students. It covers forums, the study plan with graded items and averages, challenges with rankings, follows and support messages, and an admin panel. The UI text and docs are in Spanish.
- The original spec is `project.md`.
- `PROYECTO.md` documents the features and design decisions. Keep it updated when adding features; the spec requires it.
- `docs/` holds the full technical documentation (13 numbered Spanish markdown files plus `docs/README.md` as the index). Update the relevant file when changing models, services, pages or business rules. Check numbers stated in the docs (credits, counts) against the code or DB before writing them.

## Commands

Always use the existing `.venv` (Python 3.13).

```bash
make create       # .env from .env.example, install requirements-dev.txt, pre-commit install
make up           # docker compose (PostgreSQL 16 + Keycloak 26 + Mailpit), wait, configure Keycloak (SMTP, app URLs), create tables + base data
make run          # streamlit run app/main.py (port APP_PORT, default 8501)
make seed-demo    # demo users (password Demo1234) and content; idempotent
make reset-db     # drop and recreate app tables (Keycloak users are NOT removed)
make purge-accounts  # delete accounts whose 7-day deletion grace period expired (app + Keycloak)
make down / make destroy   # stop containers / stop and delete volumes
make test         # pytest; SQLite in memory + AUTH_PROVIDER=local + MAIL_BACKEND=memory, no Docker needed
make lint         # pre-commit run --all-files (isort + ruff check --fix + ruff format + hygiene hooks)
```

- To run a single test: `.venv/bin/python -m pytest tests/test_challenges.py::test_ranking_orders_by_completion_and_first_bonus`.
- `pre-commit run --all-files` only checks git-tracked files. For untracked files, use `pre-commit run --files <paths>`.
- Ports: Keycloak is exposed on **8180** (8080 is taken on this machine), Postgres on 5432, and Mailpit on 1025 (SMTP) and 8025 (web UI, where all dev emails land). All can be changed in `.env`.

## Architecture

Code flows `app/views/*` (Streamlit) → `app/services/*` (business logic) → `app/db/models.py` (SQLAlchemy 2.0).

- **Services are Streamlit-free.**
  - They take a `Session` as the first argument and raise domain errors (`AuthError`, `AcademicError`, `ChallengeError`, `ForumError`, `SocialError`, `ProfileError`, all `ValueError`/`Exception` subclasses with user-facing Spanish messages).
  - Tests target this layer.
  - When adding a new error type, register it in `USER_ERRORS` in `app/ui/common.py`.
- **Session handling** (`app/db/session.py`):
  - `session_scope()` commits on exit.
  - `expire_on_commit=False`, so objects stay readable after the scope closes, but lazy relationships do not. Views render *inside* a `with session_scope()` block, and services eager-load with `selectinload`.
- **Writes from the UI always go through `common.run_action(lambda s: ..., "toast msg")`.** It opens its own transaction, shows domain errors with `st.error`, and calls `st.rerun()` on success.
  - Do not call `st.rerun()` inside a `session_scope` that has pending writes. The rerun exception triggers a rollback.
  - The current user is a detached `User`. Use `s.merge(user)` before mutating it.
- **Navigation:** `app/main.py` builds `st.navigation` from callables (`views.<x>.render`). Unauthenticated users only get the login page, and the admin page is added only for `role == "admin"`. Detail sub-views use `st.session_state` keys (`post_id`, `profile_id`, `challenge_id`).
- **Auth** (`app/services/auth.py`) is switched by `AUTH_PROVIDER`:
  - **`keycloak`**: login uses ROPC (`grant_type=password`) on the confidential client `ct-ranking-app`. Registration and password/email/name/enable changes go through the Keycloak Admin API using that client's service account (`manage-users`).
    - The realm is imported from `docker/keycloak/ct-ranking-realm.json`, which uses `${ENV}` placeholders filled from docker-compose env.
    - Keycloak 26's user profile requires firstName and lastName, or the password grant fails with "Account is not fully set up". This is why `User` has `first_name`/`last_name` and registration requires both.
    - `update_user` does GET then a full PUT on purpose.
  - **`local`**: bcrypt hashes in `users.password_hash`.
- **Academics math** (`services/academics.py`):
  - A subject's grade is the weighted, normalized average if *every* item has a weight. Otherwise it is the simple mean.
  - Semester and general averages are credit-weighted over subjects with status cursando, aprobada or reprobada that have grades. Status `pendiente` is excluded.
  - The grade scale comes from `GRADE_MIN`, `GRADE_MAX` and `GRADE_PASSING`.
- **Challenges:**
  - Global challenges are seeded in `app/db/init_db.py` (`GLOBAL_CHALLENGES`). Each references a rule code in `services/challenge_rules.py`, and rules measure the user's whole history.
  - Rule challenges auto-complete on join, on `refresh_automatic` (called on Home and Retos), or with "Verificar". Manual challenges require evidence.
  - Leaderboard score = sum of points + `ceil(points * 0.5)` for the first finisher of each challenge.
  - Visibility is global, public, the creator, or followers of the creator (`_visibility_filter`).
- **Pensum catalog:**
  - `app/data/pensums.py` (`PENSUMS`) holds static plan data: semester, code `IS<sem><nn>`, credits and category.
  - `academics.load_pensum` copies the subjects into a user's plan as `pendiente`, matching existing subjects by code or name.
  - `academics.credit_progress` computes credits per `SubjectCategory` plus a total row. It deduplicates retaken subjects by code or name, keeping the best status.
  - This feeds the "Historia académica" stacked bar chart (`views/academics.credits_chart`, also reused in the admin student detail).
- **Demo data** (`app/db/demo_data.py`):
  - 8 Software Engineering students at semesters 1 to 9, generated with seed 7.
  - Failed subjects are retaken as a new `Subject` row in the next semester.
  - Global challenges are completed only through the real rules.
- **Academic plan expanders:**
  - They use `_stateful_expander(label, key)` in `views/academics.py`.
  - Streamlit derives an expander's id from its label too, so a label that changes (grades) would reset it. The open state is therefore remembered in `st.session_state["_academics_open_expanders"]` and restored before rendering.
  - "Expandir/Colapsar todo" set those keys from an `on_click` callback.
- **Sidebar hover-to-expand:**
  - `app/ui/sidebar_hover.js` is injected once from `main.py` via `common.enable_sidebar_hover()` (`st.html` with `unsafe_allow_javascript=True`).
  - It drives Streamlit's own expand and collapse buttons (`stExpandSidebarButton`, `stSidebarCollapseButton`) and reads `section[data-testid="stSidebar"][data-collapsed]`. Re-check these selectors after upgrading Streamlit.
  - AppTest does not run JS. To test it, use a real browser: headless Firefox needs `ui.primaryPointerCapabilities=6` to report a mouse.
- **Accounts, 2FA and moderation** (`docs/14-cuentas-seguridad-y-moderacion.md`):
  - Keycloak features: email activation uses `VERIFY_EMAIL` plus `send-verify-email`. TOTP setup uses `execute-actions-email ["CONFIGURE_TOTP"]`, and the code is passed as the `otp` param of the password grant.
  - Keycloak returns the same `invalid_grant` for a wrong password, a missing or wrong OTP, and a brute-force lock. Rapid failed attempts trigger the lock (`user_temporarily_disabled`), so space them out when testing.
  - Deferred deletion lives in `services/accounts.py` (email code via `services/mailer.py`). Users with `deletion_scheduled_for` set only see the cancel page in `main.py`. Purge runs in a background thread (`app/jobs/purge_accounts.py`) or via `make purge-accounts`.
  - Blocks and reports live in `services/moderation.py`. Views hide content with `moderation.hidden_user_ids(s, viewer_id)` (blocks in both directions plus pending-deletion users) through the `exclude_author_ids`, `hidden_ids`, `hidden_creator_ids` and `exclude_ids` params.
- **Schema changes:** there is no Alembic. New tables come from `create_all`. New columns on existing tables must be added to `COLUMN_UPGRADES` in `app/db/init_db.py` (idempotent `ADD COLUMN IF NOT EXISTS`, Postgres only). Type changes or renames need `make reset-db`.

## Notes

- The entry point is `app/main.py`.
- Work happens on `main`, which is also the base branch for PRs. Commit messages are in English and grouped by area.
