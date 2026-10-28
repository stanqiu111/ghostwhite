# Shipping changes

How a Ghostwhite change moves from an idea through verification, review, and
an explicitly authorized release. This guide is for people and coding agents.
Read [CLAUDE.md](../CLAUDE.md) for the active feature plan,
[WORKFLOW.md](../WORKFLOW.md) for architecture, and the
[project constitution](../.specify/memory/constitution.md) for implementation rules.

## Where this comes from

Adapted from Landwise's [shipping guide in PR #3](https://github.com/stanqiu111/landwise-resume-career/blob/68a9ea125da6247f58df9792e136912d89314e20/docs/SHIPPING.md),
which credits Addy Osmani's
[How the Claude Code team does code review](https://x.com/addyosmani/article/2114604912520921136)
(October 2026). The process is retained; commands, risk areas, and release
assumptions below are specific to Ghostwhite.

- Use several layers: author verification, fresh review, available automated
  checks, human judgment, and a workable rollback.
- Do most verification and review before opening the pull request. Show
  evidence rather than describing a change as done without checking it.
- Have an agent review each pull request before human approval. Resolve each
  confirmed finding with a fix or a written explanation.
- Scale human attention to the risk of the change. Agent approval cannot
  substitute for required human approval.
- Limit review rounds so they converge; later rounds focus on new changes.
- Make changes easy to undo and turn escaped bugs into regression coverage.
- The person running the agent owns what it ships.

## The pipeline

### 1. Decide, then start small

Confirm the intended behavior and keep changes small and single-purpose.
Explain unfamiliar code before changing it. Put unrelated fixes in separate
changes; preserve the user's existing work.

For Spec Kit features, use the active specification, plan, and task list.
Mark implementation and acceptance tasks separately: writing a test or
attempting a blocked check is not evidence that the behavior passed.

### 2. Branch

Continue the existing task branch when one is already in use; otherwise create
a descriptive feature branch. Do not commit directly to the default or a
production branch. Inspect the checkout and remote first:

```bash
git status --short
git branch --show-current
git remote -v
git ls-remote --symref origin HEAD
```

At this guide's addition, `origin` is `stanqiu111/ghostwhite`, the remote default
branch is `after`, and microphone work is on `work`. Recheck before a future
pull request. The repository does not establish that pushing any particular
branch deploys production; do not import Landwise's `main`/Vercel assumptions.
Commit, push, merge, and deployment authorization follow the current user
instructions; this guide does not grant additional authorization.

### 3. Verify, and show the result

Use Python 3.12 and the dependencies in [requirements.txt](../requirements.txt).
Browser tooling uses Node 24, the lockfile, and Playwright from
[package.json](../package.json). Run commands from the repository root with the
virtual environment active. See [local setup](../README.md#running-locally) and
the [microphone quickstart](../specs/005-stream-microphone/quickstart.md).

| Change touches | Run and show |
| --- | --- |
| Every change | Inspect the complete diff and staged file list. Run `git diff --check` and, after staging, `git diff --cached --check`. Exclude credentials, `.env`, databases, uploads, recordings, and generated artifacts. |
| Documentation only | Check relative links, referenced paths, and commands against the actual configuration. Do not rerun the application suite solely for prose changes. |
| Django behavior | `python manage.py check`; run the affected app's tests, for example `python manage.py test streams --noinput`. For shared behavior or broader integration, run `python manage.py test --noinput` and compare unsuccessful test identities with the recorded baseline. |
| Models or migrations | `python manage.py makemigrations --check --dry-run` and `python manage.py migrate --plan`; apply migrations to a disposable local database, then run `python manage.py migrate --check` and affected tests. Review forward/backward compatibility and any irreversible data change. |
| Templates, CSS, or static assets | `python manage.py collectstatic --noinput` locally; inspect changed screens at desktop and 390 px width, keyboard focus, hover/active/disabled states, and reduced motion. Check owner, viewer, signed-out, and ended/error states where relevant. |
| Stream JavaScript | `node --test streams/js_tests/*.test.cjs` and `node --check` for each changed JavaScript file. These simulations cover lifecycle/playback logic, not real media delivery. |
| WebRTC or microphone behavior | Follow the media checks below and the manual quickstart. Prove permissions, cleanup, viewer playback, and actual delivery separately. |
| Authentication, permissions, federation, or storage | Real-database tests for authorized and denied paths, session and JWT access where applicable, ownership/visibility, FQID handling, and failure cases. Stub external federation/email calls, not database operations. |
| Dependencies | `python -m pip check` for the installed Python environment; `npm ci` and `npm audit` for Node changes. Review release notes and dependency/lockfile diffs. Record unresolved audit findings rather than silently changing unrelated versions. |

There is no repository-wide `npm run check`, lint command, or hosted-build
script in the current package configuration. Do not claim those checks ran.
New test fixtures use synthetic accounts and content. Do not test with real
credentials, private posts, production federation writes, or private recordings.

Do not stop or restart the user's running development server. Use another
local port for a second instance and configure its local node/base URL
consistently. The media harness already uses its own temporary SQLite database,
test accounts, generated tone, and loopback server on an allocated port.

#### Media evidence and current limits

```bash
node --test streams/js_tests/*.test.cjs
python streams/browser_tests/media.py --capture-only
```

The first command simulates media lifecycle failures. Capture-only mode uses
native browser media APIs with synthetic devices and explicitly injected
failure cases. Neither establishes end-to-end delivery or physical hardware.

On an approved local environment permitting WebRTC, with `CHROMIUM_PATH` set
to an installed Chrome/Chromium executable if needed:

```bash
python streams/browser_tests/media.py --baseline
python streams/browser_tests/media.py
```

The baseline is pinned to pre-feature commit
`1eb0a5bb933dbd7b632864da2dc2f90c3bb51e4a`, which must exist in local history.
The full harness checks incoming audio energy and advancing video frames with
synthetic capture. Physical microphone/permission, audible output, and manual
browser checks still follow the
[acceptance checklist](../specs/005-stream-microphone/quickstart.md#remaining-acceptance-local-computer).

The recorded cloud results at implementation commit `b4c48d1` are 78 passing
stream tests, 21 passing JavaScript tests, and 11 passing capture checks. The
full Django suite has 116 passes, 12 failures, and 72 errors; the 84 unsuccessful
tests match the prior baseline. This is not a green full suite. The managed
cloud Chromium policy blocks WebRTC transport and disallows ordinary capture
and fullscreen. Do not bypass it or repeatedly retry the same blocked check.
See [validation evidence](../specs/005-stream-microphone/validation.md) for the
observed timeout and policies. Local validation is separate; this document
does not mark it passed or complete feature 004 T020.

### 4. Review before the pull request

For code changes, have the diff reviewed with fresh context by a separate
review session or subagent. Supply the specification, constitution, changed
diff, and actual test evidence. Check behavior, error paths, lifecycle races,
access rules, and whether assertions establish the claimed result.

Verify findings before fixing them. Record pre-existing problems separately;
do not expand the change to repair unrelated failures. High-risk changes also
need a security-focused review. Documentation review checks factual accuracy,
links, commands, and unsupported promises.

### 5. Open the pull request

When authorized, push the feature branch and open a pull request against the
verified integration/default branch (`after` when this guide was added).
Include:

- What changed and why, including the resulting user behavior.
- Risk tier and its reason.
- Test commands and results, relevant UI evidence, baseline failures, and
  every unverified case with its blocker.
- How to revert, including effects a code revert cannot undo.

State the exact tested commit. The person running the agent is responsible
for these claims being true. A push alone is not a merge or release.

### 6. Automated checks

No `.github/workflows` or automated deployment gate is checked into this
repository at this guide's addition. [Procfile](../Procfile) specifies
`gunicorn ghostwhite.wsgi`; it does not prove a hosting provider, preview
deployment, release command, or branch trigger is configured.

Inspect whatever checks actually appear on the pull request. Resolve new
failures before merging. Disclose known baseline failures and blocked
acceptance explicitly; a human decision about a documented exception is not
a passing result. Never disable checks just to make a change appear green.

### 7. Review on the pull request

Post the review with the commit SHA and concrete findings. Each confirmed
finding gets a fix commit or a short explanation in its thread. Pre-existing,
unrelated findings are tracked separately.

Limit review to three rounds. After the first, review the new diff and affected
behavior. If the third round still finds unresolved problems, rethink the
approach with the owner. New commits are not covered by an older approval.

### 8. Approval, scaled by risk

Use the highest tier touched by the change.

**High:** owner reviews the diff and evidence; include security-focused review.
This includes authentication/session/JWT behavior, permissions and moderation,
private data and visibility, federation/network requests, uploads, database
migrations, microphone capture/consent/privacy, production settings, deployment
or security checks, new dependencies, and major dependency upgrades. Relevant
areas include `authors/`, `nodes/`, `inbox/`, `entries/`, `streams/`, migrations,
`ghostwhite/settings.py`, `Procfile`, and dependency files; classify by behavior,
not the directory alone.

**Medium:** clean review, applicable passing checks or explicitly reviewed
baseline exceptions, and owner inspection of the evidence. This includes
other application/frontend logic, tests, minor/patch dependency upgrades, and
documentation that promises privacy, retention, limits, or timing.

**Low:** clean review and applicable checks. This includes other documentation,
CSS-only styling, and wording that makes no behavioral promises.

An agent's approval never counts as human approval. The owner merges unless
they explicitly delegate merging in the current conversation. Authorization
already granted in that conversation remains valid; do not ask for it again.
Deployment requires its own applicable authorization.

### 9. After merging and an authorized release

Merging does not prove deployment or apply database migrations. Before release,
confirm the actual host, tested commit, environment configuration, database
backup/restore plan, migration order, and rollback compatibility. Use that
host's documented release process; this repository has no universal deploy
command. Do not infer one from the Procfile.

After an authorized release, verify the deployed commit, startup/error logs,
static assets, sign-in, and changed owner/viewer or permission flows. For media
changes, use the approved real-browser acceptance checks. Record migration and
smoke-check outcomes without secrets. Delete the merged branch only when no
ongoing task needs it and the owner has authorized cleanup.

### 10. When something goes wrong

The person who landed the change coordinates the fix. Use the configured
host's rollback process or a reviewed revert of the faulty commit. First check
whether the older code works with the current schema and data. A code revert
does not undo a migration, restore deleted data, or revoke exposed credentials.
Do not invent a kill switch or run destructive down-migrations without an
approved recovery plan.

After recovery, add a meaningful regression test or update this guide or
[WORKFLOW.md](../WORKFLOW.md) with the lesson. Identify which verification or
review layer should have caught the problem.

## What people still decide

The owner decides what should be built, reviews architecture and high-risk
changes, checks that evidence supports the claims, accepts any documented
remaining limitation, and owns what reaches users.

## Not yet established here

These are not claims about configured GitHub or hosting settings:

- Branch protection, required checks, approval counts, and force-push rules
  must be inspected/configured separately. A sole owner cannot approve their
  own GitHub pull request; human review may remain a documented convention.
- Automated PR review and CI are not supplied by this document. If added,
  use least-privilege permissions, pinned action revisions, and never execute
  untrusted fork code with repository secrets.
- Hosting, deployment triggers, preview environments, monitoring, and a tested
  rollback runbook need explicit project configuration and verification.
- No merge queue, staged rollout, or new feature-flag system is introduced.
  Follow the constitution's scope rule rather than adding infrastructure for
  hypothetical needs.
