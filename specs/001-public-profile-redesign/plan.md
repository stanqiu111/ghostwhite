# Technical Plan: Public Author Profile Page — Design Improvement

**Spec**: `spec.md` | **Status**: Ready to implement
**Scope**: CSS-only + minimal HTML text change. No model/migration/serializer/view/URL changes.

---

## Affected Files

| File | Change type |
|---|---|
| `authors/static/authors/author_public.css` | CSS improvements — 7 targeted edits |
| `authors/templates/authors/author_public.html` | HTML — 1 text change only |

`static/css/main.css` is NOT touched.

---

## Change Breakdown

### 1 — Avatar size increase (FR-006)

`.pub-profile-card .profile-picture` currently: `width: 90px; height: 90px; margin: -34px auto 12px;`

New: `width: 110px; height: 110px; margin: -44px auto 14px;`

The negative margin must increase proportionally so the avatar still overlaps the hero strip cleanly. The strip is 68px tall; the avatar's top half (55px) should sit above the strip base, so `-44px` centres the overlap visually.

No HTML structure change needed — the `profile-picture` div already exists.

---

### 2 — Entry content line-clamp (FR-007)

`.entry-content` currently has no height constraint. Long entries overwhelm the feed.

Add to `.entry-content`:
```css
display: -webkit-box;
-webkit-line-clamp: 4;
-webkit-box-orient: vertical;
overflow: hidden;
```

This is purely additive (no HTML change). Short entries are unaffected — `line-clamp` only truncates when content exceeds 4 lines.

---

### 3 — Stats row dividers (FR-009)

`.stats` already has a top and bottom border. The three stat items have no visual separator between them.

Add:
```css
.stat:not(:last-child) {
  border-right: 1px solid #f0f0f0;
}
```

This draws a subtle divider between "Entries | Followers | Following" without adding extra HTML.

---

### 4 — Friend grid: remove bullet and fix empty text (FR-008)

The `.friend-grid` is a `<ul>`. Browser default list styling adds a bullet marker to each `<li>`. The empty state `<li class="empty-state">` shows a bullet.

CSS fix (removes bullets from all items including the empty state):
```css
.friend-grid {
  list-style: none;
  padding: 0;
  margin: 0;
}
```

HTML fix (one text node change in `author_public.html`):
- `"Nothing"` → `"No friends yet"`

---

### 5 — Page fade-in animation (FR-011)

`main.css` has `@keyframes heart-pop`, `skeleton-sweep`, and `toast-in` but no general page-load animation.

Define `@keyframes pub-fade-in` in `author_public.css` (scoped name avoids conflict):
```css
@keyframes pub-fade-in {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
.main-container {
  animation: pub-fade-in 0.35s ease forwards;
}
```

Apply only to `.main-container` (not `body`) to avoid header flash.

---

### 6 — 480px breakpoint and mobile button (FR-010)

Existing breakpoint at 768px stacks columns. Missing: tighter padding at 480px for phones.

Add:
```css
@media (max-width: 480px) {
  .main-container {
    padding: 12px;
    gap: 12px;
  }
  .card {
    padding: 16px;
  }
  .pub-profile-card {
    padding: 0 16px 20px;
  }
}
```

Follow button already has `padding: 12px 16px` which satisfies the 44px tap-target requirement via line-height on the text.

---

### 7 — Username size bump (cosmetic)

`.username` is `font-size: 18px`. Bump to `20px` for a stronger profile name anchor.

---

## What is NOT changing

- All Django template variables — unchanged
- Follow/Unfollow JS logic — untouched
- `follow_status` relationship classes on `body` and `.pub-profile-card` — unchanged
- Any model, migration, serializer, view, or URL file
- `static/css/main.css`
- Entry card click-to-navigate / avatar stop-propagation behavior

---

## Testing

1. Start dev server: `python manage.py runserver 8765`
2. Log in as testuser (password: `Test1234!`)
3. Navigate to another user's profile — check green hero strip, avatar overlap, badge, stats dividers, line-clamped entries
4. Navigate to own profile (`/authors/testuser/`) — check purple strip, "Your Profile" badge, no Follow button
5. Resize to 375px — verify single column, no horizontal scroll
6. Resize to 480px — verify padding tightens
7. Open a profile with a long entry — verify text clamps at 4 lines
8. Click a card — verify navigation works
