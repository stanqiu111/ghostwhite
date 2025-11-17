### Identity & Profile

| Endpoint                                   | Purpose                                                              | User Story ID                  | Notes |
|--------------------------------------------|----------------------------------------------------------------------|--------------------------------|-------|
| `GET /api/authors/{username}/`             | Retrieve a public profile for the given username                    | Identity US 1.3.1, 1.5.1       | Public-facing profile page. Other authors can view this profile if allowed. |
| `PUT /api/authors/{username}/`             | Fully update an author's data (by username)                         | Identity US 1.6.1, 1.7.1       | Used for replacing the entire profile object; usually owner/admin. |
| `PATCH /api/authors/{username}/`           | Partially update an author (by username)                            | Identity US 1.6.1, 1.7.1       | Used by the frontend when only some profile fields change. |
| `GET /api/authors/author_profile/`         | Retrieve the logged-in user's own profile                           | Identity US 1.6.1, 1.7.1       | Used for the "My Profile" page. |
| `PUT /api/authors/author_profile/`         | Fully update the logged-in user's own profile                       | Identity US 1.6.1, 1.7.1       | Replaces all profile fields for the current user. |
| `PATCH /api/authors/author_profile/`       | Partially update the logged-in user's profile                       | Identity US 1.6.1, 1.7.1       | For updating small profile parts (e.g., profile image only). |
| `POST /api/authors/sync-repos/`            | Import recent GitHub activity and create public entries             | Identity US 1.4.1              | Creates new entries based on GitHub commits/events. |
| `POST /api/authors/register/`              | Register a new author (requires admin approval)                     | Node Mgmt US 8.3.1             | Sign-up flow for new local authors. Admin must approve. |
| `POST /api/authors/token/refresh/`         | Refresh access token                                                 | Identity foundation            | Keeps session active; required for authenticated operations. |

### Entries – Creation / Update / Delete / Visibility

| Endpoint                                      | Purpose                                                              | User Story ID                                      | Notes |
|-----------------------------------------------|----------------------------------------------------------------------|----------------------------------------------------|-------|
| `POST /api/entries/create/`                   | Create a new entry (plain text, markdown, optional image)           | Posting US 2.1.1, 2.5.1, 2.6.1, 2.7.1, 2.8.1       | Supports CommonMark markdown and optional image uploads. |
| `PUT /api/entries/{id}/update/`               | Fully update an existing entry                                       | Posting US 2.3.1                                   | Replaces the entire entry; updated version becomes visible in streams. |
| `PATCH /api/entries/{id}/update/`             | Partially update an entry                                            | Posting US 2.3.1                                   | Often used for changing only visibility or text. |
| `DELETE /api/entries/{id}/delete/`            | Soft-delete an entry                                                 | Posting US 2.9.1; Visibility US 4.9.1, 4.10.1      | Entry becomes invisible to users but still stored internally. |
| `GET /api/entries/`                           | Retrieve stream of visible entries                                   | Reading US 3.1.1–3.1.5; Visibility US 4.x          | Returns entries according to visibility rules (public, unlisted, friends-only). |
| `GET /api/entries/{id}/`                      | Retrieve a single entry                                              | Visibility US 4.2.1, 4.3.1, 4.6.1, 4.7.1, 4.8.1    | Access depends on visibility and relationship (friend, follower, etc.). |
| `GET /api/authors/{author_id}/entries/{id}/image` | Retrieve an image entry or the attached image                     | Posting US 2.7.1; Node Mgmt US 8.1.1              | Image hosting endpoint for markdown image links or image entries. |

### Following & Friends

| Endpoint                                   | Purpose                                                              | User Story ID                         | Notes |
|--------------------------------------------|----------------------------------------------------------------------|---------------------------------------|-------|
| `POST /api/authors/{author_id}/follow/`    | Send a follow request to another author                             | Following US 6.1.1, 6.2.1             | Supports both local and (future) remote follow workflows. |
| `DELETE /api/authors/{author_id}/follow/`  | Unfollow an author                                                   | Following US 6.5.1, 6.7.1             | Removes follower/friend relation; prevents access to friends-only entries. |
| `GET /api/authors/follow-requests/`        | View pending incoming follow requests                                | Following US 6.4.1                    | Used by the “Follow Requests” section in the UI. |
| `POST /api/authors/follows/{id}/decision/` | Accept or reject a follow request                                    | Following US 6.3.1, 6.6.1, 6.8.1      | Updates followers, following, and mutual friendship state. |

### Comments & Likes

| Endpoint                                                     | Purpose                                                   | User Story ID           | Notes |
|--------------------------------------------------------------|-----------------------------------------------------------|-------------------------|-------|
| `POST /api/entries/{id}/addcomments/`                        | Add a comment to an entry                                | Comments/Likes US 7.1.1 | Comment visibility follows entry visibility rules (public/friends-only). |
| `PUT /api/entries/{id}/comments/{comment_id}/`               | Fully update a comment                                   | Comments/Likes US 7.6.1 | Only the comment owner may update. |
| `PATCH /api/entries/{id}/comments/{comment_id}/`             | Partially update a comment                               | Comments/Likes US 7.6.1 | Used for minor text edits. |
| `DELETE /api/entries/{id}/comments/{comment_id}/`            | Delete a comment                                         | Comments/Likes US 7.6.1 | Soft-deletes comment; still counted internally. |
| `POST /api/entries/{id}/like/`                               | Like an entry                                            | Comments/Likes US 7.2.1, 7.4.1 | Updates like count; propagated to inbox if relevant. |
| `DELETE /api/entries/{id}/like/`                             | Unlike an entry                                          | Comments/Likes US 7.2.1 | Toggles like state. |
| `POST /api/entries/{id}/comments/{comment_id}/like/`         | Like a specific comment                                  | Comments/Likes US 7.3.1 | Allowed only if user can see the comment. |
| `DELETE /api/entries/{id}/comments/{comment_id}/like/`       | Unlike a specific comment                                | Comments/Likes US 7.3.1 | Toggles like state. |

### Remote Inbox & Node Sharing

| Endpoint                              | Purpose                                                                   | User Story ID                                      | Notes |
|--------------------------------------|---------------------------------------------------------------------------|----------------------------------------------------|-------|
| `POST /api/authors/{author_id}/inbox/` | Receive posts/likes/comments from other nodes                            | Posting US 2.2.1, 2.4.1, 2.10.1; Sharing US 5.2.1; Following US 6.2.1; Comments/Likes US 7.x | Core endpoint for federation; currently supports local testing and future multi-node expansion. |

### Notifications

| Endpoint                                | Purpose                                                              | User Story ID      | Notes |
|-----------------------------------------|----------------------------------------------------------------------|--------------------|-------|
| `GET /api/inbox/following-activity/`    | Show recent activity from authors I follow                           | Notifications US 9.1.1 (partial) | Used on the home dashboard; lightweight activity summary. |
| `GET /api/inbox/notifications/`         | Retrieve notifications related to my content (likes/comments/etc.)   | Notifications US 9.1.1            | Used by `/inbox/` page; supports pagination (limit parameter). |

### API Schema

| Endpoint        | Purpose                                   | User Story ID      | Notes |
|-----------------|-------------------------------------------|--------------------|-------|
| `GET /api/schema/` | Provide OpenAPI schema for API documentation | Node Mgmt US 8.5.1 | Used by Swagger UI (drf-spectacular). |
