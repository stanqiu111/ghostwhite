## Part 1 Scope – User Story Coverage

| Endpoint | Purpose | User Story ID | Notes |
|-----------|----------|---------------|-------|
| `/api/authors/register/` | Create an author account | Identity US 1.3.1 | Creates a public profile that others can link to |
| `/api/authors/login/` | Obtain JWT pair | Identity foundation | Needed for all private operations |
| `/api/authors/token/refresh/` | Refresh access token | Identity foundation | Keeps sessions alive |
| `/api/authors/author_profile/` | Read or update own profile | Identity US 1.3.1 | Shows and edits current user details |
| `/api/entries/` | List entries that require auth | Reading US 3.1.1 seed | Single node stream for Part 1 |
| `/api/entries/create/` | Create an entry | Posting US 2.1.1 | Supports plain text, markdown, and optional image |
| `/api/entries/{entry_id}/` | Read a public entry | Visibility US 4.2.1 baseline | Works without auth |
| `/api/entries/{entry_id}/update/` | Update an entry | Posting US 2.3.1 | Owner only |
| `/api/entries/{entry_id}/delete/` | Soft delete an entry | Visibility US 4.10.1 | Owner only |
| `/api/entries/{entry_id}/addcomments/` | Comment on an entry | Comments US 7.1.1 | Auth required |
| `/api/entries/{entry_id}/like/` | Toggle like on an entry | Likes US 7.2.1 | Auth required |
| `/api/entries/{entry_id}/comments/{comment_id}/like/` | Toggle like on a comment | Likes US 7.3.1 | Auth required |
| `/api/authors/{author_id}/follow/` | Send follow request | Following US 6.2.1 baseline | Auth required |
| `/api/authors/follow-requests/` | List pending follow requests | Following US 6.5.1 seed | Auth required |
| `/api/authors/follows/{follow_id}/decision/` | Accept or deny a follow request | Following US 6.4.1 | Auth required |
