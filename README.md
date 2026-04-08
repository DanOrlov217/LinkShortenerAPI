# Link Shortener API

## Project Description

This project implements a FastAPI service for shortening URLs. The service allows users to create short links that redirect to long URLs, search for already created short links, and view statistics on them. Registered users can also view their link history, as well as delete and update their links.

---

## Project Structure

All link and user data is stored in a PostgreSQL database. Alembic is used for migrations. Caching of popular links is implemented with Redis, which speeds up redirects for short URLs.

Celery is used to delete expired links by periodically checking the database and removing outdated records. Celery is also used to update the cache by periodically checking link popularity.

---

## Database Models

### `user` — Registered Users

The table is created by the `fastapi-users` library with fields for email, password hash, and activity/verification flags. One additional field is added:

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `email` | string | Email address (unique) |
| `hashed_password` | string | Password hash |
| `is_active` | bool | Whether the account is active |
| `is_verified` | bool | Whether the email is verified (not used) |
| `is_superuser` | bool | Superuser flag (not used) |
| `registered_at` | timestamptz | Registration date and time |

### `short_links` — Active Short Links

| Field | Type | Description |
|---|---|---|
| `id` | integer | Primary key |
| `original_url` | string | Original URL |
| `short_code` | string | Unique short code (alias) |
| `created_at` | timestamptz | Creation date |
| `last_accessed_at` | timestamptz | Date of last access |
| `access_count` | integer | Number of accesses |
| `expires_at` | timestamptz | Link expiration date |
| `owner_id` | UUID (FK) | Link owner (NULL for anonymous) |

### `expired_links` — Link History

Stores an archive of links deleted manually by the owner or expired automatically.

| Field | Type | Description |
|---|---|---|
| `id` | integer | Primary key |
| `original_url` | string | Original URL |
| `short_code` | string | Short code |
| `created_at` | timestamptz | Link creation date |
| `expired_at` | timestamptz | Deletion/expiration date |
| `access_count` | integer | Number of accesses during the link's lifetime |
| `deleted_by_user` | bool | `true` — deleted manually, `false` — expired |
| `owner_id` | UUID (FK) | Link owner |

---

## Authentication Endpoints

### `POST /auth/register` — Register a New User

Field validation:
- `email` — must contain the `@` character
- `password` — length between 8 and 128 characters

```json
{
  "email": "user@example.com",
  "password": "strongpassword"
}
```

### `POST /auth/jwt/login` — Log In, Returns a JWT Token

```
Content-Type: application/x-www-form-urlencoded

username=user@example.com&password=strongpassword
```

### `POST /auth/jwt/logout` — Log Out (requires authentication)

```
Authorization: Bearer <token>
```

---

## Link Endpoints

### `POST /links/shorten` — Create a Short Link

Available to all users. Authenticated users become the link owner and can update or delete it. The `expires_at` and `custom_alias` fields are optional.

If `expires_at` is not provided, the link expires 30 days after creation. Supported formats:

| Format | Example |
|---|---|
| `YYYY-MM-DD HH:MM` | `2026-12-31 23:59` |
| `YYYY-MM-DDTHH:MM:SSZ` | `2026-12-31T23:59:00Z` |
| `YYYY-MM-DDTHH:MM:SS` | `2026-12-31T23:59:00` |

```json
{
  "url": "https://example.com/very/long/url",
  "expires_at": "2026-12-31 23:59",
  "custom_alias": "my-link"
}
```

### `GET /links/search?original_url=<url>` — Search Short Links by Original URL

```
GET /links/search?original_url=https://example.com/very/long/url
```

### `GET /links/{short_code}` — Redirect via Short Link

```
GET /links/my-link
```

Returns a `302` redirect to the original URL. Popular links are cached in Redis.

### `GET /links/{short_code}/stats` — Short Link Statistics

```
GET /links/my-link/stats
```

Returns information about the link: original URL, creation date, expiration date, last access date, and access count.

### `PUT /links/{short_code}?new_url=<url>` — Update Original URL (requires authentication, owner only)

```
PUT /links/my-link?new_url=https://new-example.com
Authorization: Bearer <token>
```

### `DELETE /links/{short_code}` — Delete a Link (requires authentication, owner only)

The deleted link is saved to history.

```
DELETE /links/my-link
Authorization: Bearer <token>
```

### `POST /links/history` — User Link History (requires authentication)

Returns a paginated list of the user's expired and deleted links.

```json
{
  "page": 1,
  "limit": 20
}
```

```
Authorization: Bearer <token>
```

---

## Running the Application

### Requirements

- Docker and Docker Compose

### 1. Clone the Repository

```bash
git clone <repo-url>
cd AppliedPython_Project_3
```

### 2. Create a `.env` File

Create a `.env` file in the project root with the following content:

```dotenv
DB_USER=postgres
DB_PASS=postgres
DB_HOST=db_app
DB_PORT=1221
DB_NAME=url_shortener

AUTH_SECRET=your-secret-key

REDIS_URL=redis://redis_app:5370
```

### 3. Start the Containers

```bash
docker compose up --build
```

After startup:

| Service | Address |
|---|---|
| API (FastAPI) | http://localhost:9999 |
| Swagger Docs | http://localhost:9999/docs |
| Flower (Celery monitor) | http://localhost:5555 |

### 4. Apply Migrations

Migrations are applied automatically when the `app` container starts (the `docker/app.sh` script runs `alembic upgrade head` before starting the server).

---

## Testing

### Stack

| Tool | Purpose |
|---|---|
| `pytest` + `pytest-asyncio` | Async test runner |
| `SQLAlchemy` + `aiosqlite` | In-memory SQLite — no real DB needed |
| `httpx` | Async HTTP client for API tests |
| `unittest.mock.AsyncMock` | Redis mock — no real Redis needed |
| `locust` | Load / performance testing |

### Unit Tests — `LinkService`

Located in `tests/links/test_service.py`. Tests the service layer directly against the in-memory database, covering:

- `create_link` — short code generation, custom aliases, conflict detection, owner assignment, custom expiry
- `get_link` — existing, missing, and expired links
- `use_link` — access count increment, `last_accessed_at` update
- `update_link` — URL change, wrong-owner rejection
- `delete_link` — row removal, `ExpiredLink` archive creation, wrong-owner rejection
- `delete_expired` — bulk expiry cleanup, owned vs anonymous archiving
- `search_links` — URL match, expired-link exclusion

### API Tests — `tests/test_api.py`

Full HTTP-level tests using an `AsyncClient` with the database and Redis mocked out:

- `POST /links/shorten` — anonymous, authenticated, custom alias, duplicate alias
- `GET /links/{short_code}` — redirect, unknown code
- `GET /links/{short_code}/stats` — existing link, 404
- `GET /links/search` — match, empty result
- `DELETE /links/{short_code}` — own link, unauthenticated (401), another user's link (404)
- `PUT /links/{short_code}` — own link, unauthenticated (401), another user's link
- `POST /links/history` — unauthenticated (401), empty history
- `POST /auth/register` — new user, duplicate email (400)
- `POST /auth/jwt/login` — valid credentials, wrong password (400)

### Load Tests — `tests/test_load.py`

Uses [Locust](https://locust.io/) to simulate realistic traffic against a live server. Two user classes are defined:

| User class | Traffic share | Behaviour |
|---|---|---|
| `AnonymousUser` | ~80 % | shorten, redirect, stats, search |
| `RegisteredUser` | ~20 % | register, login, shorten, update, delete, history |

**Interactive UI** (open http://localhost:8089 to configure and start the test):

```bash
locust -f tests/test_load.py --host http://localhost:9999
```