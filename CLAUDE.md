# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

CT Ranking is a Streamlit platform for university students. It covers forums, the study plan with graded items and averages, challenges with rankings, follows and support messages, and an admin panel. The UI text and docs are in Spanish.
- The original spec is `docs/enunciado.md`.
- `docs/resumen-del-proyecto.md` documents the features and design decisions. Keep it updated when adding features; the spec requires it.
- `docs/` holds the full technical documentation (15 numbered Spanish markdown files plus `docs/README.md` as the index). Update the relevant file when changing models, services, pages or business rules. Check numbers stated in the docs (credits, counts) against the code or DB before writing them.

## Commands

The app and its services run in containers (`container/`), with Docker or Podman. The local `.venv` (Python 3.13) is only for tests, lint and format.

```bash
make up           # build app image, start db/keycloak/mailpit, run `setup` (wait, configure Keycloak, init_db), start app on :8501
make dev          # like up, but mounts app/ and scripts/ read-only and reloads on save (container/compose.dev.yaml)
make run          # rebuild the image and restart only the app container
make shell        # bash in a fresh app container; make logs / make ps
make init-db      # create tables + base data only (what setup does last)
make seed-demo    # demo users (password Demo1234) and content; idempotent
make reset-db     # drop and recreate app tables (Keycloak users are NOT removed)
make purge-accounts  # delete accounts whose 7-day deletion grace period expired (app + Keycloak)
make migrate-emails  # move existing students' emails to STUDENT_EMAIL_DOMAIN (ARGS=--dry-run to preview)
make down / make destroy   # stop containers / stop and delete volumes
make create       # .env from .env.example, .venv with requirements-dev.txt, pre-commit install
make test         # pytest in .venv; SQLite in memory + AUTH_PROVIDER=local + MAIL_BACKEND=memory, no containers needed
make lint         # pre-commit run --all-files (isort + ruff check --fix + ruff format + hygiene hooks)
make format       # isort + ruff check --fix + ruff format on app, tests, scripts
```

- `tests/test_audit_validation.py` holds regression tests for the findings in `AUDITORIA.md` (the technical audit report, in Spanish).
- Tests use the `session` fixture (fresh in-memory SQLite with foreign keys on) and `make_user(**kwargs)` (registers through `auth.register`) from `tests/conftest.py`. Sent emails land in `mailer.OUTBOX`.
- To run a single test: `.venv/bin/python -m pytest tests/test_challenges.py::test_ranking_orders_by_completion_and_first_bonus`.
- `pre-commit run --all-files` only checks git-tracked files. For untracked files, use `pre-commit run --files <paths>`.
- Ports: Keycloak is exposed on **8180** (8080 is taken on this machine), Postgres on 5432, the app on 8501, and Mailpit on 1025 (SMTP) and 8025 (web UI, where all dev emails land). All are published on `127.0.0.1` only (`BIND_ADDRESS`) and can be changed in `.env`.
- **Containers** (`container/`, details in `docs/03-despliegue-y-operacion.md`):
  - `ENGINE` defaults to docker if installed, else podman (`make up ENGINE=podman`). `COMPOSE` is `$(ENGINE) compose --env-file .env -f container/compose.yaml`; `--env-file` is needed because compose otherwise looks for `.env` next to the compose file.
  - The app image (`container/Dockerfile`, `python:3.13-slim`, user `app` uid 10001) bakes in the code; `.env` comes in via `env_file` and is excluded by the root `.dockerignore`. Code changes need `make run` unless using `make dev`.
  - Compose overrides `POSTGRES_HOST=db`, `POSTGRES_PORT=5432`, `KEYCLOAK_URL=http://keycloak:8080` and empties `DATABASE_URL` for the app; `.env` values with `localhost` only apply on the host. `SMTP_HOST` is *not* overridden and must be `mailpit` (Makefile warns on `localhost`).
  - The browser still reaches Keycloak at `KEYCLOAK_PUBLIC_URL` (`KC_HOSTNAME`, issuer of tokens). `KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true` lets the app use the internal URL; this keeps `st.login` working when the metadata URL is internal.
  - `secrets.toml` is written at container start to `STREAMLIT_SECRETS_FILE=/home/app/.streamlit/secrets.toml` (named volume `streamlit`; Streamlit reads `~/.streamlit/secrets.toml` too).
  - Podman compatibility rules: fully qualified image names, `z` on bind mounts (SELinux), never write to host bind mounts (rootless UID mapping), healthchecks in compose rather than the Dockerfile.

## Architecture

Code flows `app/ui/pages/*` (Streamlit) → `app/services/*` and `app/auth/*` (logic) → `app/database/models.py` (SQLAlchemy 2.0).

Package map:
- `app/core/`: `config.py` (`get_settings`, `.env`), `mailer.py` (SMTP or the in-memory `OUTBOX`) and `ratelimit.py` (in-process attempt limits; tests reset it in an autouse fixture). Callers pass `error=` a domain error such as `AuthError`, because the default `RateLimitError` is not in `USER_ERRORS`.
- `app/database/`: `models.py`, `session.py`, `init_db.py` (CLI, `SCHEMA_UPGRADES`/`CHECK_UPGRADES`), and `seeds/` with `base.py` (admin and global challenges), `demo.py` and `pensums.py` (catalog).
- `app/auth/`:
  - `service.py` holds the public API.
  - `keycloak.py`, `validation.py`, `passwords.py` and `errors.py` support it, and `accounts.py` handles deferred deletion.
  - `app/auth/__init__.py` re-exports the API, so callers do `from app import auth` and `auth.login(...)`.
- `app/services/`: one module per domain (academics, challenges, challenge_rules, forum, social, users, moderation, admin).
- `app/ui/`:
  - `pages/` has one `render()` per page.
  - `components/` has `session` (current user, logout, OIDC), `actions` (`run_action`, `flash`, `USER_ERRORS`), `formatting`, `widgets`, `charts`, `rankings`, `moderation`, `support` (`support_dialog`) and `sidebar`. Pages must not import from other pages; shared UI goes in `components/`.
  - `assets/` holds the JavaScript.
- Pages must not use local variable names that shadow imported component modules (`actions`, `session`, …). That bug already happened once.

- **Services are Streamlit-free.**
  - They take a `Session` as the first argument and raise domain errors (`AuthError`, `AccountError`, `AdminError`, `AcademicError`, `ChallengeError`, `ForumError`, `SocialError`, `ProfileError`, `ModerationError`, plus `MailError` from `core/mailer.py`, all with user-facing Spanish messages).
  - Pages do not query the ORM directly (`select(...)`, `s.get(Model, …)`); add a service function instead (e.g. `users.get_user`, `users.list_users`, `challenges.get_challenge`).
  - Admin-only service functions take the acting user (`actor`) and check `actor.is_admin` themselves (`admin.set_role`, `admin.delete_message`).
  - Tests target this layer.
  - When adding a new error type, register it in `USER_ERRORS` in `app/ui/components/actions.py`.
- **Session handling** (`app/database/session.py`):
  - `session_scope()` commits on exit and rolls back on exceptions, except subclasses of `CommitBeforeRaiseError`, which commit and re-raise. `accounts.InvalidCodeError` uses it so failed code attempts survive the UI's rollback.
  - `expire_on_commit=False`, so objects stay readable after the scope closes, but lazy relationships do not. Views render *inside* a `with session_scope()` block, and services eager-load with `selectinload`.
- **Writes from the UI always go through `actions.run_action(lambda s: ..., "toast msg")`.** It opens its own transaction, shows domain errors with `st.error`, and calls `st.rerun()` on success.
  - Do not call `st.rerun()` inside a `session_scope` that has pending writes. The rerun exception triggers a rollback.
  - `run_action` also turns an `IntegrityError` (double click inserting the same row) into a toast.
  - The current user is a detached `User`. Use `s.merge(user)` before mutating it.
  - `main.py` calls `session.current_user()` once per rerun and stores it in `st.session_state["_current_user"]`; pages call `session.require_user()`, which reuses it. Password sessions expire after `SESSION_TTL_HOURS` (`session.start_session` records `_login_at`).
  - `User.avatar` is `deferred`. Do not read it from a detached user; use `user.has_avatar` and `users.avatar_bytes(session, id)` (the UI caches the data URI in `widgets._avatar_data_uri`, keyed by `avatar_updated_at`).
  - Any user-provided text inserted with `unsafe_allow_html=True` must go through `html.escape` (see `widgets.user_chip`); app emails escape it too.
- **Navigation:** `app/main.py` builds `st.navigation` from callables (`ui.pages.<x>.render`). Unauthenticated users only get the login page. Accounts pending deletion only get `ui/pages/account_pending.py`. The admin page is added only for `role == "admin"`. Detail sub-views use `st.session_state` keys (`post_id`, `profile_id`, `challenge_id`).
- **Auth** (`app/auth/service.py`) is switched by `AUTH_PROVIDER`:
  - **`keycloak`**: login uses ROPC (`grant_type=password`) on the confidential client `ct-ranking-app`. Registration and password/email/name/enable changes go through the Keycloak Admin API using that client's service account (`manage-users`).
    - The realm is imported from `container/keycloak/ct-ranking-realm.json`, which uses `${ENV}` placeholders filled from the compose env.
    - Keycloak 26's user profile requires firstName and lastName, or the password grant fails with "Account is not fully set up". This is why `User` has `first_name`/`last_name` and registration requires both.
    - `update_user` does GET then a full PUT on purpose.
    - `KeycloakClient` shares a `requests.Session` and caches the service-account token until shortly before it expires.
    - `_sync_keycloak_user` matches by `keycloak_id`, then by verified email on an unlinked row. Never by username (Google derives it from the email). New rows get a free username (`carlos2`).
    - **The app DB owns the role.** Keycloak's `admin` realm role is only applied when the local row is created; `admin.set_role` changes persist.
  - **`local`**: bcrypt hashes in `users.password_hash`.
- **Email change** (`auth/accounts.py`): `request_email_change` sends a 6-digit code to the new address; `confirm_email_change` applies it via `auth.apply_verified_email` (Keycloak `emailVerified=true`). Never set an email as verified without that code. Codes (deletion and email) share `_issue_code`/`_consume_code`: 15 min, 5 attempts, 1 per minute, HMAC with `APP_SECRET_KEY`.
- **Academics math** (`services/academics.py`):
  - A subject's grade is the weighted, normalized average if *every* item has a weight. Otherwise it is the simple mean.
  - Semester and general averages are credit-weighted over subjects with status cursando, aprobada or reprobada that have grades. Status `pendiente` is excluded.
  - The grade scale comes from `GRADE_MIN`, `GRADE_MAX` and `GRADE_PASSING`.
- **Challenges:**
  - Global challenges are seeded in `app/database/seeds/base.py` (`GLOBAL_CHALLENGES`). Each references a rule code in `services/challenge_rules.py`, and rules measure the user's whole history.
  - Rule challenges auto-complete on join, on `refresh_automatic` (called on Home and Retos), or with "Verificar". Manual challenges require evidence.
  - Leaderboard score = sum of points + `ceil(points * 0.5)` for the first finisher of each challenge. It is computed in SQL (`_scores_query`: `ROW_NUMBER` per challenge, integer `//` for the bonus). Users pending deletion are excluded, including from deciding who finished first. Use `challenges.standing(s, user_id)` for one user's score/position instead of loading the whole board.
  - `challenges.creator_id` is `ON DELETE SET NULL`; `accounts.purge_due_accounts` deletes the user's community challenges explicitly and keeps global ones.
  - Visibility is global, public, the creator, or followers of the creator (`_visibility_filter`).
- **Pensum catalog:**
  - `app/database/seeds/pensums.py` (`PENSUMS`) holds static plan data: semester, code `IS<sem><nn>`, credits and category.
  - `academics.load_pensum` copies the subjects into a user's plan as `pendiente`, matching existing subjects by code or name.
  - `academics.credit_progress` computes credits per `SubjectCategory` plus a total row. It deduplicates retaken subjects by code or name, keeping the best status.
  - This feeds the "Historia académica" stacked bar chart (`ui/components/charts.credits_chart`, also reused in the admin student detail).
- **Demo data** (`app/database/seeds/demo.py`):
  - 8 Software Engineering students at semesters 1 to 9, generated with seed 7.
  - Failed subjects are retaken as a new `Subject` row in the next semester.
  - Global challenges are completed only through the real rules.
- **Academic plan expanders:**
  - They use `_stateful_expander(label, key)` in `ui/pages/academics.py`.
  - Streamlit derives an expander's id from its label too, so a label that changes (grades) would reset it. The open state is therefore remembered in `st.session_state["_academics_open_expanders"]` and restored before rendering.
  - "Expandir/Colapsar todo" set those keys from an `on_click` callback.
- **Sidebar hover-to-expand:**
  - `app/ui/assets/sidebar_hover.js` is injected once from `main.py` via `sidebar.enable_sidebar_hover()` (`st.html` with `unsafe_allow_javascript=True`).
  - It drives Streamlit's own expand and collapse buttons (`stExpandSidebarButton`, `stSidebarCollapseButton`) and reads `section[data-testid="stSidebar"][data-collapsed]`. Re-check these selectors after upgrading Streamlit.
  - AppTest does not run JS. To test it, use a real browser: headless Firefox needs `ui.primaryPointerCapabilities=6` to report a mouse.
- **Two-step password login:**
  - `auth.begin_login` first verifies the password through the `ct-ranking-pwcheck` client. That client is bound to the "direct grant - solo contraseña" flow, a copy without the OTP step, created by `configure_keycloak.py`.
  - Only if the user has an OTP credential does the UI ask for the code. It then calls `auth.login(..., otp)` on the main client, where Keycloak validates it.
  - The password waits in `st.session_state` for at most 5 minutes.
  - This is needed because the main direct grant flow returns the same error for a wrong password and a missing OTP.
- **Accounts, 2FA and moderation** (`docs/14-cuentas-seguridad-y-moderacion.md`):
  - Keycloak features: email activation uses `VERIFY_EMAIL` plus `send-verify-email`. TOTP setup uses `execute-actions-email ["CONFIGURE_TOTP"]`, and the code is passed as the `otp` param of the password grant.
  - Keycloak returns the same `invalid_grant` for a wrong password, a missing or wrong OTP, and a brute-force lock. Rapid failed attempts trigger the lock (`user_temporarily_disabled`), so space them out when testing.
  - Deferred deletion lives in `auth/accounts.py` (email code via `core/mailer.py`). Users with `deletion_scheduled_for` set only see the cancel page (`ui/pages/account_pending.py`). Purge runs in a background thread (`app/jobs/purge_accounts.py`) or via `make purge-accounts`.
  - Blocks and reports live in `services/moderation.py`. Views hide content with `moderation.hidden_user_ids(s, viewer_id)` (blocks in both directions plus pending-deletion users) through the `exclude_author_ids`, `hidden_ids`, `hidden_creator_ids` and `exclude_ids` params. Counts (comments, likes, `social.follow_counts(..., hidden_ids)`) must exclude them too.
  - `ct-ranking-pwcheck` tokens skip OTP, so `configure_keycloak.py` gives that client `fullScopeAllowed: false` and only the `basic` scope (no roles, no audience). The app only reads `sub` from it.
- **Google login** (`docs/15-inicio-sesion-con-google.md`):
  - It uses `st.login("google")`, an OIDC Authorization Code flow against Keycloak. `authorize_params = {kc_idp_hint = "google"}` makes Keycloak jump straight to Google.
  - `secrets.toml` is generated from the env by `scripts/write_streamlit_secrets.py` when the app container starts (in the container, `~/.streamlit/secrets.toml`; locally `.streamlit/secrets.toml`, gitignored).
  - `scripts/configure_keycloak.py` creates the Google IdP (`hostedDomain` = institutional domain, username = email local part) only when `GOOGLE_CLIENT_ID` is set, and removes it otherwise.
  - There are two identical `st.login` providers, `google` (sign in) and `googlesignup` (sign up). Streamlit forbids `_` in provider names. Streamlit stores the provider name in `st.user["provider"]`, and that is the only way to know the intent after the redirect.
  - `session.sync_oidc_session()` calls `auth.login_with_oidc(..., allow_create=provider == "googlesignup")`, which re-validates the domain.
  - Without `allow_create`, the account must already exist (matched by `keycloak_id` or email). Otherwise it raises `AccountNotFoundError` and deletes the broker-only user Keycloak just created.
  - The cookie keeps Google sessions across reloads.
  - Requires `authlib` and `httpx`.
- **Schema changes:** there is no Alembic. New tables come from `create_all`. New columns on existing tables must be added to `SCHEMA_UPGRADES` in `app/database/init_db.py` (idempotent, Postgres only); new `CHECK` constraints to `CHECK_UPGRADES`. Indexes declared in the models are created automatically on existing tables (`Index.create(checkfirst=True)`). Type changes or renames need `make reset-db`.
- **Scripts** in `scripts/` run as modules from the repo root, `/app` in the image (`python -m scripts.configure_keycloak`); they do not touch `sys.path`. Only `app/main.py` keeps its `sys.path.insert` because `streamlit run` puts `app/` on the path.

## Notes

- The entry point is `app/main.py`.
- Work happens on `main`, which is also the base branch for PRs. Commit messages are in English and grouped by area.
