# Quickstart Validation: Live Stream Feature

**Date**: 2026-07-06 | **Plan**: [plan.md](plan.md) | **Contract**: [contracts/streams-api.md](contracts/streams-api.md)

## Prerequisites

```bash
cd /Users/stanqiu/f25-project-ghostwhite
source venv/bin/activate
python manage.py migrate          # applies streams/0001_initial
python manage.py runserver 8000
```

Two local user accounts (any existing users work — e.g. `stan` and `Test User`).

## Automated validation

```bash
python manage.py test streams            # new feature tests
python manage.py test                    # full suite — must stay green (SC-005)
python manage.py check
```

Expected: all pass, 0 issues.

## Manual scenario walkthrough

### S1 — Start a stream (User Story 1)

1. Log in as user A → open `http://127.0.0.1:8000/streams/` → click **Start stream**.
2. Submit title "Test stream" + a description.
3. **Expect**: redirected to the stream detail page; status shows **Live**; start time is now; placeholder player area visible.
4. Submitting an empty title re-renders the form with a validation error and creates nothing.
5. Trying to start a second stream while live → blocked with "You already have a live stream."

### S2 — Discover and watch (User Story 2)

1. Log in as user B (different browser/incognito).
2. Open `/streams/` → **Expect**: user A's stream listed with streamer name, title, start time.
3. Click it → **Expect**: detail page shows streamer, title, description, **Live**, player placeholder — and **no End button** (B is not the owner).
4. Log out → open `/streams/` → **Expect**: redirect to login.

### S3 — End a stream (User Story 3)

1. As non-owner B: `curl -X POST http://127.0.0.1:8000/api/streams/<serial>/end/ -H "Authorization: Bearer <B's token>"` → **Expect 403**, stream still live.
2. As owner A on the detail page: click **End stream** → **Expect**: status flips to **Ended**, end time shown, End button gone.
3. Refresh `/streams/` → **Expect**: stream no longer listed (empty state if it was the only one).
4. Open the ended stream's URL directly → **Expect**: page loads, shows **Ended** with start + end times.
5. POST `/end/` again as owner → **Expect 200**, `endedAt` unchanged (idempotent).

### Regression sweep

- Home feed, entry detail, profile page, and inbox all load and behave as before (SC-005).
- `python manage.py collectstatic --noinput` succeeds (WhiteNoise manifest includes `streams/streams.css`).
