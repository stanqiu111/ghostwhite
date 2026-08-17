# Tasks: Public Author Profile Page — Design Improvement

**Spec**: `spec.md` | **Plan**: `plan.md`
**Dependency order**: CSS edits → HTML text → manual test

All changes are in `authors/static/authors/author_public.css` (CSS) and `authors/templates/authors/author_public.html` (one text node).

---

## User Story 1 — Visitor reads profile clearly

- [x] **T-01** CSS — Increase avatar size: `.pub-profile-card .profile-picture` → `width: 110px; height: 110px; margin: -44px auto 14px;`
- [x] **T-02** CSS — Add entry content line-clamp: add `-webkit-line-clamp: 4` rules to `.entry-content`
- [x] **T-03** CSS — Add stats row dividers: `.stat:not(:last-child) { border-right: 1px solid #f0f0f0; }`
- [x] **T-04** CSS — Bump username font size from `18px` to `20px`

## User Story 2 — Mobile user browses profiles

- [x] **T-05** CSS — Add `@media (max-width: 480px)` breakpoint for tighter padding on phones
- [x] **T-06** CSS — Verify follow button tap target (padding audit — no change needed if already ≥44px)

## User Story 3 — Relationship context instant (polish)

- [x] **T-07** CSS — Remove bullets from friend grid: add `list-style: none; padding: 0; margin: 0` to `.friend-grid`
- [x] **T-08** HTML — Change empty state text: `"Nothing"` → `"No friends yet"` in `author_public.html` line ~189
- [x] **T-09** CSS — Add page fade-in: define `@keyframes pub-fade-in` and apply to `.main-container`

---

## Manual Verification

- [ ] **V-01** Own profile → purple strip + "Your Profile" badge + no Follow button
- [ ] **V-02** Friend profile → green strip + "✓ Friends" badge
- [ ] **V-03** Stranger profile → indigo strip + "Follow" button visible
- [ ] **V-04** Long entry in feed → text clamped at 4 lines
- [ ] **V-05** 375px viewport → single column, no horizontal scroll
- [ ] **V-06** 480px viewport → padding is tighter than 768px view
- [ ] **V-07** Friend grid empty state → italic text, no bullet point
- [ ] **V-08** Card click still navigates to entry
- [ ] **V-09** Avatar click still navigates to that author's profile (stopPropagation intact)
