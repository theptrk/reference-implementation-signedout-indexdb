# Todo Starter

A runnable bootstrap project generated from [Cookiecutter Django](https://github.com/cookiecutter/cookiecutter-django), then extended with the local-to-cloud todo pattern.

- Landing page explains the guest and account feature sets.
- Guests add, edit, complete, filter, and delete todos in IndexedDB. No todo data is sent to the server.
- Accounts use email/password or Google sign-in. Account todos live in the server database and are available from other devices.
- On the first authenticated visit to `/app/`, browser todos are imported, acknowledged, and removed from IndexedDB. Import failures preserve the local copy. Retrying cannot create duplicates, including after a cloud todo is deleted.
- Integrations provides a separate Google Calendar connection and displays the next 10 events in the primary calendar. It requests read-only event access; it does not create calendar events or synchronize todos with Calendar.

## Run locally

Install [uv](https://docs.astral.sh/uv/). It installs the pinned Python 3.14 runtime automatically.

```sh
cd todo_starter
uv sync --locked
uv run python manage.py migrate
uv run python manage.py runserver
```

Open http://localhost:8000. SQLite is automatic locally; no PostgreSQL or Redis service is needed. Local email is printed to the terminal: follow the verification link there after signing up. Email verification remains mandatory, including in production.

Optional credentials:

```sh
cp .env.example .env
# Fill in Google settings, then:
uv run --env-file .env python manage.py runserver
```

Use one consistent origin: `localhost` and `127.0.0.1` have separate browser storage. IndexedDB and Web Locks require a modern browser on localhost or HTTPS. This app stores guest data locally; a service worker/offline app shell is not included. Cloud changes appear after refreshing the list.

## Google setup

1. Create a Google Cloud project and a Web application OAuth client. Configure the consent screen and add development test users.
2. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`. Enable Google Calendar API for Calendar access.
3. Register both redirect URIs exactly:
   - `http://localhost:8000/accounts/google/login/callback/` for allauth sign-in.
   - `http://localhost:8000/integrations/google/callback/` for Calendar consent.
4. Generate a stable key: `uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`. Set `GOOGLE_TOKEN_ENCRYPTION_KEY` to its output. Keep it with application secrets and preserve it across releases; changing it requires reconnecting existing Calendar accounts.
5. Start the server with `.env`, sign in, and open Integrations. Google sign-in requests only identity scopes. Calendar asks for `calendar.events.readonly`, offline access, and explicit consent, with state and PKCE validation.

Production uses HTTPS redirect URIs and `GOOGLE_CALENDAR_REDIRECT_URI` must match the registered Calendar callback. Google may require OAuth app verification; refresh tokens for external apps in Testing can expire. Live OAuth requires real credentials and is not exercised by the mocked automated tests.

Calendar refresh/access tokens are encrypted in the database. Disconnect deletes this application's saved credentials; it does not revoke the Google grant. Users can revoke it from their Google account permissions. Password accounts can connect Calendar without using Google for sign-in.

## Reuse as a bootstrap template

From the parent repository:

```sh
python3 scripts/bootstrap.py my_new_app /tmp/my_new_app
```

This copies and renames the app, Python package, settings references, tests, and metadata. It excludes environments, databases, `.env`, caches, and uploads. Review the resulting author, license, domain, and production settings before releasing.

## Architecture and guarantees

- `config/settings/{base,local,test,production}.py`: upstream split settings, local/test SQLite, production PostgreSQL environment configuration.
- `todo_starter/users/`: upstream email-based custom user and django-allauth.
- `todo_starter/todos/`: owner-scoped JSON CRUD and transactional imports. UUID import receipts persist after todo deletion; deleting the user cascades through todos and receipts.
- `todo_starter/static/js/todos.js`: browser CRUD, same-origin API calls with CSRF, Web Locks around guest operations/imports, cross-tab notifications, and retry handling.
- `todo_starter/integrations/`: separate Calendar OAuth grant, encrypted credentials, refresh, read-only upcoming events, disconnect.

Every authenticated API request carries its page's account ID, checked against the active session. A stale tab cannot silently import into a different account. Guest mutations recheck session identity before writing. Import validates an entire batch before writing, commits todos and receipts together, and returns acknowledged IDs. The browser deletes its database only after all batches succeed. A failed cleanup retries safely. On PostgreSQL, imports serialize per user. SQLite is for local development and tests.

Signing out returns to guest mode with a fresh browser list; cloud todos are never copied to IndexedDB. A shared browser's guest todos go into the next account that signs in. Guests should sign in to the intended account. Only this app's guest database is removed, never unrelated origin databases. Clearing site data before importing loses guest todos.

## Checks

```sh
uv run pytest
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
```

Tests cover ownership, CSRF, stale accounts, import idempotency and rollback, validation, Calendar state/expiry/PKCE, token encryption, and disconnect. Upstream user tests are retained.

## Production

Use `DJANGO_SETTINGS_MODULE=config.settings.production`, PostgreSQL (`DATABASE_URL`), Redis (`REDIS_URL`), `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_ADMIN_URL`, and production Google settings. Configure SMTP (`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`) and `DJANGO_DEFAULT_FROM_EMAIL`. Run migrations and collectstatic, then serve `config.wsgi:application` with Gunicorn behind HTTPS. Keep database and encryption-key backups. The upstream HSTS setting starts at 60 seconds; increase it after validating HTTPS. User uploads are not used in this reference.

## Scaffold provenance

Generated on 2026-10-23 from the official Cookiecutter Django `main` archive with: project_name=Todo Starter, project_slug=todo_starter, username_type=email, cloud_provider=None, mail_service=Other SMTP, use_whitenoise=y, use_docker=n. The generated `uv.lock` pins resolved dependencies. SQLite support, the UI, todo features, Calendar integration, and bootstrap copier are additions to the generated scaffold. The scaffold retains its MIT license.
