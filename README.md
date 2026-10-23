# reference-implementation-signedout-indexdb

A runnable Django reference for an app that works before sign-up and adds account-based storage after sign-in. The example is a todo list generated from [Cookiecutter Django](https://github.com/cookiecutter/cookiecutter-django), with email/password accounts, Google sign-in, and a separate Google Calendar integration.

Use this as a working example or bootstrap project. The repository name uses `indexdb`; the browser API implemented here is **IndexedDB**.

## Behavior at a glance

| State | Todo storage | Available across devices? |
| --- | --- | --- |
| Signed out | IndexedDB in the current browser and origin | No |
| Signed in | Server database, scoped to the authenticated user | Yes, using the same account |
| On sign-in | Existing browser todos move to the account; IndexedDB is deleted after confirmation | Yes, after transfer |

Both states support adding, editing, completing, filtering, and deleting todos. Account holders can also connect Google Calendar to view upcoming events. Todos are not synchronized with Calendar.

## How an AI agent should use this repository

1. Decide whether to copy this starter into a new project or adapt its pattern to an existing application.
2. Read the browser controller, todo views, and models together. The transfer guarantee depends on both client and server; copying only the import endpoint is insufficient.
3. Read the settings and user app before changing authentication. The project already has an email-based custom user model and django-allauth. For an existing project, integrate with its accounts and migrations instead of replacing them.
4. Preserve the storage rules below when adapting todos to another domain model. Keep account ownership, CSRF, stale-session checks, import receipts, and acknowledgement-before-deletion.
5. Keep Google sign-in separate from Calendar authorization. Password accounts can connect Calendar later; Google sign-in alone does not authorize Calendar access.
6. Keep the user interface explicit about signed-in versus signed-out behavior. The signed-out todo page has one explanation banner plus a loading/save/error indicator. Avoid repeating the explanation in badges, extra alerts, and footnotes. Change styles only when requested.
7. Run the checks and verify the running page, including email verification and password reset. These pages inherit allauth layouts. A server started without autoreload can keep serving cached templates even after source files change.

Never copy local databases, `.env`, uploaded files, virtual environments, encryption keys, or real user data into a new project or public repository. Do not assume this example implements offline operation, real-time sync, or Calendar writes.

## Run locally

Install [uv](https://docs.astral.sh/uv/); it installs the pinned Python 3.14 runtime.

```sh
cd todo_starter
uv sync --locked
uv run python manage.py migrate
uv run python manage.py runserver 127.0.0.1:8000
```

Check that the port is free before starting a server. Open `http://localhost:8000/` for the landing page and `/app/` for todos. Keep using the same hostname, scheme, and port: IndexedDB is origin-scoped, so `localhost`, `127.0.0.1`, and different ports have separate lists.

Local development and tests use SQLite by default, without PostgreSQL or Redis services. Production uses the upstream PostgreSQL and Redis configuration.

**Local email is printed to the server terminal, not delivered to an inbox.** Follow the verification link printed there after signing up. Email verification remains mandatory. Production needs working SMTP.

Optional settings:

```sh
cp .env.example .env
# Edit .env, then:
uv run --env-file .env python manage.py runserver 127.0.0.1:8000
```

## Bootstrap a new project

From this repository's root:

```sh
python3 scripts/bootstrap.py my_new_app /tmp/my_new_app
cd /tmp/my_new_app
uv sync --locked
uv run python manage.py migrate
uv run python manage.py runserver
```

The copier renames the Python package and its references. It excludes local data, credentials, environments, caches, and uploads. The destination must not exist; the project name must be a lowercase Python identifier. Review the resulting author, license, domain, database names, copy, OAuth callbacks, and deployment settings.

For an existing Django app, port the relevant components deliberately. Do not overwrite its settings, user model, or migration history with the starter's.

## Files to read

All paths are relative to this repository. The nested `todo_starter/todo_starter/` path is intentional: the outer directory is the project root, and the inner directory is the application package.

| Concern | File or directory |
| --- | --- |
| Environment settings | [`todo_starter/config/settings/`](todo_starter/config/settings/) |
| Root routes | [`todo_starter/config/urls.py`](todo_starter/config/urls.py) |
| Custom user and allauth adapters | [`todo_starter/todo_starter/users/`](todo_starter/todo_starter/users/) |
| Todos and import receipts | [`todo_starter/todo_starter/todos/models.py`](todo_starter/todo_starter/todos/models.py) |
| CRUD, validation, owner isolation, import | [`todo_starter/todo_starter/todos/views.py`](todo_starter/todo_starter/todos/views.py) |
| IndexedDB, transfer, browser UI | [`todo_starter/todo_starter/static/js/todos.js`](todo_starter/todo_starter/static/js/todos.js) |
| Landing page | [`todo_starter/todo_starter/templates/pages/home.html`](todo_starter/todo_starter/templates/pages/home.html) |
| Todo page and state explanation | [`todo_starter/todo_starter/templates/todos/app.html`](todo_starter/todo_starter/templates/todos/app.html) |
| Verification and other account-page layout | [`todo_starter/todo_starter/templates/allauth/layouts/entrance.html`](todo_starter/todo_starter/templates/allauth/layouts/entrance.html) |
| Calendar OAuth, encryption, refresh, events | [`todo_starter/todo_starter/integrations/`](todo_starter/todo_starter/integrations/) |
| New-project copier | [`scripts/bootstrap.py`](scripts/bootstrap.py) |

## Storage transition: rules to preserve

Transfer runs when an authenticated user opens `/app/`, including after the normal login redirect. Creating an account or opening an unrelated page does not itself transfer the data.

1. The browser acquires a Web Lock and checks that the session matches the account rendered into the page. Signed-out writes use the same lock.
2. It reads existing todos from the `todo-starter-guest` IndexedDB database. Each has a UUID.
3. It sends batches of up to 1,000 todos to the import endpoint.
4. The server validates the entire batch before writing. It creates account todos and import receipts inside a database transaction.
5. The server acknowledges processed local UUIDs. The browser checks every acknowledgement.
6. Only after all batches succeed does the browser delete this app's IndexedDB database. New signed-in todos go directly to the server.

Important failure behavior:

- Failed requests or missing acknowledgements preserve the browser database for retry.
- Todos and their receipts commit together; failed todo creation must not leave an import receipt behind.
- Receipts are unique per user and local UUID. Retrying a batch does not duplicate todos.
- Receipts survive todo deletion, preventing an old retry from resurrecting a deleted todo.
- Failed browser cleanup can be retried after server success because receipts prevent duplicate imports.
- PostgreSQL imports lock the user row to serialize same-account imports. The default SQLite tests do not establish PostgreSQL concurrency behavior.
- Signing out never copies account todos back to IndexedDB. After a successful transfer, a new signed-out list starts empty.

On a shared browser, unsigned-in todos go into the next account that signs in. The app cannot identify who originally typed those todos.

## API contract

Requests are same-origin. Authentication uses Django session cookies. Mutations require CSRF protection. Authenticated todo requests additionally carry `X-Account-ID`, checked against the active session to catch stale tabs after account switches. This header is a consistency check, not an authentication credential.

| Method | Route | Behavior |
| --- | --- | --- |
| GET | `/app/session/` | Current user ID or `null` |
| GET / POST | `/app/api/todos/` | List owned todos / create one |
| PATCH / DELETE | `/app/api/todos/<uuid>/` | Update / delete an owned todo |
| POST | `/app/api/todos/import/` | Import local todos and acknowledge their IDs |

Todo JSON uses `id`, `title`, and `completed`. Titles must contain 1–300 characters after trimming; `completed` must be a boolean. Import requests use `{"todos": [{"id": "<uuid>", "title": "Example", "completed": false}]}` and return `{"acknowledged": ["<uuid>"]}`. The browser controller shows header and CSRF handling.

Signed-out todo data is not sent to the server. Session-status checks still make network requests; browser storage does not imply zero network activity.

## Google setup

See [the application setup guide](todo_starter/README.md#google-setup) and [`.env.example`](todo_starter/.env.example).

- Google sign-in needs `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
- Calendar additionally needs `GOOGLE_TOKEN_ENCRYPTION_KEY` and `GOOGLE_CALENDAR_REDIRECT_URI`.
- Register `/accounts/google/login/callback/` for sign-in and `/integrations/google/callback/` for Calendar, including the actual hostname, scheme, and port.
- Calendar requests `calendar.events.readonly`, with offline access, state validation, and PKCE. It displays the next 10 primary-calendar events.
- Access and refresh tokens are encrypted with Fernet. Keep the stable encryption key outside source control and preserve it across releases.
- Disconnect deletes saved app credentials; it does not revoke the Google-side grant.

The app runs without Google credentials. Automated tests mock Google responses; live OAuth has not been verified with production credentials in this reference.

## Validation

From `todo_starter/`:

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
```

The current suite has 39 tests, covering the upstream user functionality plus ownership, CSRF, validation, stale-account imports, retries, rollback, Calendar state/expiry/PKCE, encrypted credentials, and disconnect.

Browser smoke test using disposable local data:

1. Add and edit a signed-out todo; reload and confirm it remains.
2. Sign up, follow the terminal's verification link, and sign in.
3. Open `/app/`; confirm the todo is in the account and this app's IndexedDB database is removed.
4. Sign in to the same account in a separate browser session and confirm the todo is available.
5. Sign out and confirm account todos are not shown as a signed-out list.
6. Check email verification and password reset as well as custom login/signup pages.

## Limits and production setup

- IndexedDB is persistent browser storage. The UI phrase “browser memory” does not mean an in-memory JavaScript array. Clearing site data loses unsigned-in todos.
- No offline app shell or service worker is included. Signed-out writes also require the server to be reachable for the session check.
- Cross-device updates require refresh. There are no WebSockets, background polling, or conflict resolution.
- Calendar is read-only; there is no todo-to-event export or two-way Calendar sync.
- Console email and SQLite are local conveniences. Production SMTP, PostgreSQL, and live Google OAuth need environment-specific configuration and verification.

Production uses `config.settings.production`, PostgreSQL, Redis, a unique `DJANGO_SECRET_KEY`, allowed hosts, a private admin URL, SMTP, HTTPS, and production Google callbacks. Run migrations and `collectstatic`, then serve `config.wsgi:application` using Gunicorn behind HTTPS. See [production settings](todo_starter/README.md#production). Development secret defaults apply only to local/test settings.

## Provenance and license

Generated from the official Cookiecutter Django `main` archive on 2026-10-23 and extended with this example. The upstream commit was not recorded; `todo_starter/uv.lock` pins resolved application dependencies. Generation choices are recorded in [the application README](todo_starter/README.md#scaffold-provenance).

MIT licensed; see [LICENSE](LICENSE).
