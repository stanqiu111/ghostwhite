# ÉTHÉRÉ — A Distributed Social Network

A federated social networking platform where independent server **nodes** exchange posts,
follows, comments, and likes with each other over a shared HTTP inbox protocol. Built with
Django and Django REST Framework.

Originally developed as a six-person team project for CMPUT 404 (Web Applications and
Architecture) at the University of Alberta, and extended since — see
[Attribution](#attribution).

---

## What it does

- **Federation** — nodes authenticate to each other with HTTP Basic auth and POST activity
  objects to `/api/authors/<id>/inbox`. A remote author is stored in the same table as a
  local one, distinguished only by which `Node` it belongs to.
- **FQID identity** — every object's primary key is a fully-qualified URL
  (`http://host/api/authors/<uuid>/entries/<uuid>`), which is what makes objects portable
  across nodes without an ID-collision or translation layer.
- **Posts (entries)** with plain-text, Markdown, and base64 image content, four visibility
  levels (public / unlisted / friends-only / soft-deleted), comments, and likes.
- **Follows and friends** — a follow is a request the recipient approves or denies; mutual
  accepted follows constitute friendship, which gates friends-only content.
- **Live streams** — WebRTC browser-to-browser screen sharing where the server acts purely
  as a REST signaling relay (no media server, no WebSockets), plus a bullet-curtain
  (danmaku) comment overlay, persistent chat, opt-in microphone commentary and
  [cross-node viewing](docs/FEDERATED_STREAMING.md).
- **GitHub activity import** — a linked GitHub account's public events become entries.

Start with the [documentation index](docs/README.md) for setup, frontend conventions, federation, testing, and shipping. For architecture, read [WORKFLOW.md](WORKFLOW.md).

## Architecture

```
Browser
  ├── Django Templates (HTML pages)   ← /home/, /entries/<pk>/, /authors/<username>/
  └── REST API (JSON)                 ← /api/...
        ├── JWT Auth      ← regular users (Bearer token)
        └── Basic Auth    ← remote nodes only

Django apps:
  authors   → users, follows, GitHub integration, email verification
  entries   → posts, comments, likes
  nodes     → federated node registry
  inbox     → receives activity from remote nodes, notifications
  streams   → live streams, WebRTC signaling relay, bullet curtain
  utils     → FQID helpers, node communication, inbox parsing
```

**Stack:** Python 3.12, Django 5.1.1, Django REST Framework, SimpleJWT, SQLite (dev) /
PostgreSQL (supported through `DATABASE_URL`), WhiteNoise, Gunicorn.

## Running locally

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # edit before loading; settings read environment variables
set -a
. ./.env
set +a
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

The app is then at http://127.0.0.1:8000/. Log in through `/authors/auth/`.

New accounts require **admin approval** before they can log in — approve them in
`/admin/` by setting `approved` and `is_active` on the Author. If you configure email,
accounts also require email verification.

### Configuration

Start with [`.env.example`](.env.example) for local configuration. The important variables:

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | Django secret key. **Required.** No default in production. |
| `DJANGO_DEBUG` | `1` for local development; explicitly set `0` in production. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames. Required when `DEBUG` is off. |
| `DATABASE_URL` | Postgres connection string. Falls back to SQLite when unset. |
| `EMAIL_BACKEND` | Console email locally; select Django's SMTP backend when configuring outgoing email. |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | Credentials for the configured SMTP service. |

### Setting up federation

Follow [node setup](docs/NODE_SETUP.md) for reciprocal node records and credentials.
Outbound federation uses the sending node’s local credentials; the receiving node
registers those credentials on its remote-node record. For live streams, also follow
[the streaming extension](docs/FEDERATED_STREAMING.md).

## Tests

```bash
python manage.py test            # full suite
python manage.py test streams    # a single app
```

**Recorded baseline at `228bee1`:** 99 stream tests pass. The full suite has 137 passes,
12 failures and 72 errors across the older apps. Many involve URL reversing and the
transition to FQID primary keys. These are unresolved baseline failures; a passing
stream suite does not mean the full application suite passes. See
[validation evidence](specs/006-federated-streams/validation.md) and the
[frontend checks](docs/FRONTEND.md#verification).

## API documentation

Interactive OpenAPI docs (drf-spectacular / Swagger UI) are served at `/api/docs/` when the
server is running. See also [API reference](docs/API.md) and
[Inbox protocol](docs/INBOX_API_FLOW.md) for the federation protocol in detail.

## Attribution

This project began as a CMPUT 404 group project. The original team, all of whom hold
copyright in the initial work:

| Name | GitHub |
|---|---|
| Jueun (Krystal) Kim | [@rlawndms](https://github.com/rlawndms) |
| Evelyn Nguyen | [@LinhNguyen310](https://github.com/LinhNguyen310) |
| Stan Qiu | [@stanqiu111](https://github.com/stanqiu111) |
| Ximeng Duan | [@XimengDuan](https://github.com/XimengDuan) |
| Michael Yang | [@MichaelY223](https://github.com/MichaelY223) |
| Shuran Kong | [@arinnaaa](https://github.com/arinnaaa) |

Commit history in this repository is preserved from the original project, so each
contributor's work remains attributed to them.

## License

MIT — see [LICENSE](LICENSE).
