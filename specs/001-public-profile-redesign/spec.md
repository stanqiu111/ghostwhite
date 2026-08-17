# Feature Specification: Public Author Profile Page — Design Improvement

**Feature Branch**: `001-public-profile-redesign`
**Created**: 2026-06-15
**Status**: Approved for implementation

---

## User Scenarios & Testing

### User Story 1 — Visitor reads a profile clearly (Priority: P1)

A logged-in user navigates to another author's public profile. They immediately understand:
- Who this person is (name, avatar, relationship to them)
- How active they are (entry/follower/following counts)
- What the person has posted (entry feed)

**Why this priority**: Core purpose of the profile page.

**Independent Test**: Open any public profile URL while logged in. All three pieces of info are immediately visible without scrolling.

**Acceptance Scenarios**:
1. **Given** a profile with an avatar, **When** the page loads, **Then** the avatar is prominently displayed and overlaps the hero strip cleanly with no clipping or overlap artifacts.
2. **Given** a profile page, **When** viewed at 1280px wide, **Then** the three-column layout (profile sidebar / feed / my-profile sidebar) is visible and well-proportioned.
3. **Given** a long entry in the feed, **When** it appears in the card, **Then** the text is clamped to ~4 lines with no runaway walls of text.

---

### User Story 2 — Mobile user browses profiles (Priority: P2)

A user on a phone (~375px–768px wide) opens a public profile.

**Why this priority**: Project is tested on mobile in user story evaluations.

**Independent Test**: Resize browser to 375px wide. Profile card, entry feed, and buttons must all be usable without horizontal scrolling.

**Acceptance Scenarios**:
1. **Given** a 375px viewport, **When** the page loads, **Then** the layout stacks to a single column with the entry feed on top and profile card below.
2. **Given** a mobile viewport, **When** the Follow/Unfollow button is shown, **Then** it is full-width and easily tappable (min-height 44px).
3. **Given** a mobile viewport, **When** the friend grid has entries, **Then** avatars are at least 48px and names are readable.

---

### User Story 3 — User understands relationship context instantly (Priority: P3)

The visual design communicates the viewer's relationship to the profile owner (self / friend / pending / stranger) without requiring the user to read any labels.

**Why this priority**: Already partially implemented via hero strip color and badge. This story polishes the signal-to-noise ratio.

**Acceptance Scenarios**:
1. **Given** viewing a friend's profile, **When** the page loads, **Then** the green hero strip and "✓ Friends" badge are visible before any scroll.
2. **Given** viewing own profile, **Then** the purple strip and "Your Profile" badge are shown, and no Follow button appears.
3. **Given** the friend grid is empty, **When** rendered, **Then** no bullet point or stray list marker appears next to the empty state message.

---

## Requirements

### Functional (CSS/template only — no backend changes)

- **FR-001**: All existing Django template variables (`author`, `entries`, `follow_status`, `author_friends`, `entry_count`, `author_follower_count`, `author_following_count`, `request_user_*`) remain unchanged.
- **FR-002**: Follow/Unfollow JS logic is untouched.
- **FR-003**: Entry card click-to-navigate and avatar click-to-profile behavior are preserved.
- **FR-004**: Relationship body classes (`page-friend`, `page-self`, `page-pending`, `page-stranger`) remain on `<body>`.
- **FR-005**: Page must work for unauthenticated visitors (no Follow button, no right sidebar).

### Visual / layout

- **FR-006**: Profile avatar diameter increases from 90px to 110px.
- **FR-007**: Entry content clamped to 4 lines max with `line-clamp`.
- **FR-008**: Empty friend grid shows italic "No friends yet" text with no bullet point.
- **FR-009**: Stats row has visible divider lines between the three stats.
- **FR-010**: Responsive breakpoint at 768px stacks to single column; breakpoint at 480px tightens padding.
- **FR-011**: Page fades in on load (matching home.html `@keyframes page-in` pattern).
- **FR-012**: No inline `style="..."` attributes added (existing ones may remain as-is per constitution).

---

## Success Criteria

- **SC-001**: All three profile relationship states (self / friend / stranger) visually distinct on a 1280px screen.
- **SC-002**: Mobile layout (375px) shows no horizontal scroll and all interactive elements ≥ 44px tap target.
- **SC-003**: Long entry text (>4 lines) is clamped; short entries are unaffected.
- **SC-004**: No regression in follow/unfollow functionality.
- **SC-005**: No model, migration, serializer, view, or URL change.

---

## Assumptions

- Font family stays as-is (system-ui stack already set in `author_public.css`).
- The `@keyframes page-in` animation is already defined in `main.css` or is safe to define in `author_public.css` without conflict.
- Changes are CSS-only + minimal HTML structure (adding a class or wrapper at most); no JS additions needed.
- `static/css/main.css` is not modified (contains shared header/tooltip/animation code).
