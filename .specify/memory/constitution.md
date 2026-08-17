# ÉTHÉRÉ Constitution

## I. Model-First Development

Every feature that touches data **must** begin with the data model. Migrations are written and run before any view, serializer, or template code is added.

- Schema changes → migrations → models → serializers → views → templates → JS
- Never add a view that depends on a field that doesn't have a corresponding migration
- Migration files are committed alongside model changes in the same PR

## II. Dual Authentication (JWT + Django Session)

All API views and template views must support **both** authentication paths:

- `SessionAuthentication` — for server-rendered pages (Django session cookie)
- JWT `Bearer` token — for API clients and external nodes
- Views must not strip `SessionAuthentication` from `authentication_classes` unless explicitly justified
- Template pages use `request.user.is_authenticated` (session-based); JS uses `localStorage.access_token` (JWT-based). Both must work.

Prior incident: `EntryListView` overrode `authentication_classes` to session-only, silently breaking JWT clients.

## III. No Mocked Database in Tests

Integration tests **must** hit a real SQLite database. No `MagicMock`, `patch`, or in-memory object substitutes for database calls.

Prior incident: mocked tests passed while a real migration failure went undetected in production.

Acceptable mocks: external HTTP calls to remote nodes, email sending, file storage.

## IV. Serializers Own Validation and Business Logic

- Validation belongs in DRF serializers (`validate_*` methods, `validate()`), not in views
- Views are thin: authenticate → call serializer → return response
- Serializer `create()` and `update()` handle all DB writes

## V. Relationship State is Server-Side

When UI appearance depends on a relationship (friend/stranger/self/pending), the Django view **must** pass that state via template context. JS may enhance the display but must not be the sole source of truth.

Prior pattern: profile pages using `follow_status` from Django context for hero strip color and badges, not relying on async JS-only checks.

## VI. CSS in App Files, Not Inline

- No `style="..."` attributes in templates except for image sizing that is purely dimensional (width/height)
- Page-specific CSS goes in the Django app's `static/<app>/` directory
- Shared styles go in `static/css/main.css`
- Duplicate class definitions across CSS files are a conflict risk — scope page-specific classes or use unique names

## VII. Public API Contract (DRF + node federation)

- All public endpoints under `/api/` must return consistent JSON shapes — check `serializers.py` before adding new fields
- Remote node compatibility: `id` field must be the full FQID URL, `serial` is the UUID shorthand
- Visibility rules (PUBLIC/FRIENDS/UNLISTED/PRIVATE) are enforced in `EntryListView` and `InboxView`, not in serializers

## VIII. Simplicity and Scope Control

- No feature flags, no backwards-compatibility shims when code can simply be changed
- No defensive error handling for impossible states — trust model constraints and DRF's built-in validation
- Three similar lines of template code are better than a premature template tag abstraction
- If a task could ship without it, it ships without it

## Governance

This constitution supersedes all other development guidelines. Any violation requires a written justification in the PR description. Amendments require updating this file and noting the change date below.

**Version**: 1.0 | **Created**: 2026-06-15 | **Project**: ÉTHÉRÉ (CMPUT 404 Distributed Social Network)
