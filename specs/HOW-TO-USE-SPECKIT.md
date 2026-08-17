# Spec-Kit Usage Guide — ÉTHÉRÉ

Spec-Driven Development workflow for this Django 5.1.1 + DRF + JWT project.
Run these commands in Claude Code. Skills live in `.claude/skills/`, command files in `.claude/commands/`.

---

## The 5-Step Loop (run in order for every new feature)

```
/speckit-specify  →  /speckit-clarify  →  /speckit-plan  →  /speckit-tasks  →  /speckit-implement
```

Each step produces a file in `specs/NNN-feature-name/`. **No code is written until `/speckit-implement`.**

---

## Step 1 — `/speckit-specify` : Write the feature spec

Describe **what** and **why**. No tech stack yet.

### Prompt template

```
/speckit-specify
<describe what you want to build and why — focus on user value, not implementation>

Examples:
  "Users should be able to bookmark entries and view a saved feed"
  "Admins need a way to see pending follow requests across all users"
  "Public profiles should show a bio and link to the user's GitHub"
```

### Output
`specs/NNN-feature-name/spec.md` — user stories, acceptance criteria, edge cases, functional requirements.

---

## Step 2 — `/speckit-clarify` : Resolve ambiguities (recommended)

Run this after specify, before plan. Surfaces edge cases you haven't thought of.

### Prompt template

```
/speckit-clarify
```

No arguments needed — it reads the spec and asks targeted questions.
Answer the questions, then move on to plan.

---

## Step 3 — `/speckit-plan` : Generate the technical plan

Now specify the Django tech stack. This is where implementation decisions are made.

### Prompt template (copy and customize)

```
/speckit-plan
Tech stack: Django 5.1.1, Django REST Framework, JWT (SimpleJWT) + SessionAuthentication,
SQLite (dev) / PostgreSQL (prod on Heroku), server-rendered Django templates + vanilla JS.

App structure:
  - authors/     — Author model (custom user), Follow model, profile views
  - entries/     — Entry model (posts), likes, comments
  - inbox/       — Follow requests, notifications
  - nodes/       — Federated remote nodes

Key patterns to follow:
  - Model changes always come with a migration
  - Serializers own validation; views are thin
  - Template pages use request.user.is_authenticated (session); JS uses localStorage.access_token (JWT)
  - Page-specific CSS in static/<app>/<page>.css; shared styles in static/css/main.css
  - Public profile relationship state (friend/stranger/self) passed via Django context, not JS-only

<add any feature-specific constraints here>
```

### Output
`specs/NNN-feature-name/plan.md`, `data-model.md`, `research.md`, `quickstart.md`

---

## Step 4 — `/speckit-tasks` : Generate the task checklist

Breaks the plan into ordered, checkable tasks.

### Prompt template

```
/speckit-tasks
Order tasks using the Django dependency chain:
  1. DB migrations (if schema changes)
  2. Model fields / methods
  3. DRF serializers
  4. API views + URL routing
  5. Django template views + context
  6. HTML templates
  7. CSS (in static/<app>/ files)
  8. JS behaviour
  9. Tests (Django TestCase hitting real SQLite — no mocked DB)
```

### Output
`specs/NNN-feature-name/tasks.md` — checklist of tasks grouped by user story, with `[P]` markers for parallel work.

---

## Step 5 — `/speckit-implement` : Execute the tasks

Runs through `tasks.md` in order and writes code.

### Prompt template

```
/speckit-implement
```

Or to run a specific user story only:
```
/speckit-implement
Implement User Story 1 only. Stop and confirm before moving to User Story 2.
```

---

## Optional: Quality commands

### `/speckit-analyze` — Cross-check before implementing

Run after `/speckit-tasks`, before `/speckit-implement`. Finds contradictions between spec, plan, and tasks.

```
/speckit-analyze
```

### `/speckit-checklist` — Generate a quality gate

Useful for API changes or anything security-sensitive.

```
/speckit-checklist
Security and API contract review: check that new endpoints respect
JWT + SessionAuthentication dual auth, enforce visibility rules
(PUBLIC/FRIENDS/UNLISTED/PRIVATE), and don't expose unapproved author data.
```

---

## Full example — "Add bio to public profiles"

```
# Step 1
/speckit-specify
Users should be able to add a short bio to their profile.
The bio should appear on the public profile page under their display name.
Other users can read it but not edit it. Own profile page lets you edit it.

# Step 2
/speckit-clarify

# Step 3
/speckit-plan
Tech stack: Django 5.1.1, DRF, JWT + SessionAuthentication, SQLite, server-rendered templates.
Bio is stored on the Author model (TextField, optional, max 300 chars).
Edit via the existing profile settings page (authors/profile_page.html + profile.css).
Display on author_public.html in the left profile card.

# Step 4
/speckit-tasks
Order: migration → Author model → AuthorSerializer → profile view context → profile_page.html → author_public.html → profile.css → author_public.css

# Step 5
/speckit-implement
```

---

## File locations after setup

```
specs/
├── HOW-TO-USE-SPECKIT.md        ← this file
└── NNN-feature-name/
    ├── spec.md                  ← user stories + acceptance criteria
    ├── plan.md                  ← technical decisions
    ├── data-model.md            ← schema / model changes
    ├── research.md              ← stack research notes
    ├── quickstart.md            ← how to run/test the feature
    └── tasks.md                 ← implementation checklist

.specify/
├── memory/constitution.md       ← project principles (read by all speckit commands)
├── templates/                   ← spec/plan/tasks scaffolds
└── scripts/bash/                ← create-new-feature.sh, setup-plan.sh, etc.

.claude/
├── commands/speckit.*.md        ← dot-notation slash commands
└── skills/speckit-*/SKILL.md   ← hyphen-notation skills (installed by CLI)
```

---

## Key rules (from the constitution)

- **Model-first**: write migration before touching views or templates
- **No mocked DB**: tests use real SQLite (`TestCase` with real queries)
- **Dual auth**: every API view must work with both session cookie and JWT Bearer token
- **CSS in files**: no `style="..."` in templates; use `static/<app>/<page>.css`
- **Server-side state**: relationship status (friend/stranger/self) in Django context, not JS-only

Full constitution: `.specify/memory/constitution.md`

---

## CLI reference (when venv is active)

```bash
source venv/bin/activate

specify --version                        # check version
specify integration list                 # list available integrations
specify extension list                   # list installed extensions
specify self check                       # check for CLI updates

# Start a new feature branch manually (optional)
bash .specify/scripts/bash/create-new-feature.sh
```
