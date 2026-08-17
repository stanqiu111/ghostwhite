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
  (danmaku) comment overlay.
- **GitHub activity import** — a linked GitHub account's public events become entries.

For a full walkthrough of every subsystem, read [WORKFLOW.md](WORKFLOW.md).

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
PostgreSQL (production), WhiteNoise, Gunicorn.

## Running locally

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then edit .env — at minimum set DJANGO_SECRET_KEY
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

The app is then at http://127.0.0.1:8000/. Log in through `/authors/auth/`.

New accounts require **admin approval** before they can log in — approve them in
`/admin/` by setting `approved` and `is_active` on the Author. If you configure email,
accounts also require email verification.

### Configuration

All environment variables are documented in [`.env.example`](.env.example). The important
ones:

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | Django secret key. **Required.** No default in production. |
| `DJANGO_DEBUG` | `1` for local development, unset/`0` in production. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames. Required when `DEBUG` is off. |
| `DATABASE_URL` | Postgres connection string. Falls back to SQLite when unset. |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | Gmail SMTP for verification emails. Emails print to the console when unset. |

### Setting up federation

To connect two nodes, each node creates a `Node` record in `/admin/` for the other, with
the remote node's `host_url` plus the username and password that this node will use to
authenticate outbound requests to it. Credentials are per-pair and agreed between the two
node operators — never commit them.

## Tests

```bash
python manage.py test            # full suite
python manage.py test streams    # a single app
```

**Known state:** the `streams` app's 74 tests pass. Roughly 84 tests across `authors`,
`entries`, `inbox`, and `nodes` currently fail, the majority with `NoReverseMatch`. These
are stale tests written against an earlier integer/UUID primary-key scheme that were never
migrated when the project moved to FQID primary keys — the application code handles FQIDs
correctly via `utils.fqid.extract_serial_from_fqid`. Migrating them is open work.

## API documentation

Interactive OpenAPI docs (drf-spectacular / Swagger UI) are served at `/api/docs/` when the
server is running. See also [api_doc.md](api_doc.md) and
[INBOX_API_FLOW.md](INBOX_API_FLOW.md) for the federation protocol in detail.

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
