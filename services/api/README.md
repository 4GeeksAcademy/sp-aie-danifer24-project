# Nexova Incidents API

FastAPI service exposing the shared incident validation and analysis logic. It also serves the static backoffice at `/`.

## Run

From the repository root:

```bash
python -m pip install -r services/api/requirements.txt
uvicorn services.api.main:app --reload
```

Open `http://127.0.0.1:8000/`. The API documentation is available at `http://127.0.0.1:8000/docs`.

## Users and authentication

Copy `.env.example` to `.env`, set `JWT_SECRET_KEY` to a secret generated with
`openssl rand -hex 32`, and configure `ACCESS_TOKEN_EXPIRE_MINUTES` as a positive
integer. The application loads `.env` at startup; the file is excluded from Git.

- `POST /users`: public registration. Accepts `email`, `password`, and optional
	profile fields `name`, `phone`, and `address`. New users always receive the
	`user` role, and profile data is stored separately from credentials.
- `POST /auth/login`: accept JSON `email` and `password`, returning a bearer JWT.
- `GET /auth/me`: return the authenticated user's email, role, and linked
	profile; requires a bearer JWT.
- `GET /profiles/me`: return the authenticated user's profile.
- `PUT /profiles/me`: update the authenticated user's `name`, `phone`, and
	`address`; omitted fields remain unchanged and explicit `null` clears a field.
- `GET /users` and `GET /users/{id}`: require a bearer token.
- `PUT /users/{id}` and `DELETE /users/{id}`: require the account owner or an
	admin. Users may change their own email or password; only admins may change
	roles or active status.
- Every `/suppliers` and `/api/incidents` endpoint also requires a bearer JWT.
- Accessing another user's `/users/{id}` returns `403` unless the caller is an
	admin; missing or invalid authentication returns `401`.

Use `Authorization: Bearer <access_token>` for protected requests. The first
admin account must be provisioned out of band; public registration cannot assign
privileged roles.

## Endpoints

## Password recovery (Resend)

Configure these server-only environment variables in the root `.env` (never use
a `NEXT_PUBLIC_` prefix or commit secrets):

```dotenv
RESEND_API_KEY=your_resend_api_key
RESEND_FROM_EMAIL=Nexova <noreply@your-verified-domain.com>
PASSWORD_RESET_URL=http://localhost:3000/reset-password
```

Create an API key in Resend and verify the sender domain. Resend's test sender
can only deliver to permitted test recipients. Use an HTTPS application URL in
production; `PASSWORD_RESET_URL` must be an absolute URL without a query string
or fragment. It targets `uis/application`, where recovery pages are public.
Restart FastAPI after changing environment settings. No extra email dependency
is required: the backend uses Resend's HTTPS REST API with a 10-second timeout.

- `POST /auth/forgot-password`: JSON `{ "email": "user@example.com" }`.
	Existing active accounts receive an email containing a reset link. Both known
	and unknown addresses return the same HTTP 200 message, including if email
	delivery fails. A 200 response confirms receipt, not successful delivery.
	Delivery failures are logged generically without tokens, addresses or keys.
- `POST /auth/reset-password`: JSON `{ "token": "...", "new_password": "..." }`.
	Returns 200 on success or 400 for an invalid, expired or already-used token.
	Tokens are signed JWTs with a separate purpose and 30-minute expiry. Only token
	digests are persisted in TinyDB's `password_resets` table. Resetting removes all
	pending reset links for that account; they also stop working after any password
	change because they are bound to the previous password hash. Reset tokens cannot
	be used as session bearer tokens. Run a single API worker, as with other TinyDB
	writes, so validation and consumption are serialized.
- `POST /auth/change-password`: bearer session token and JSON
	`{ "current_password": "...", "new_password": "..." }`. Returns 400 if the
	current password is incorrect, 401 without a valid session, and 200 on success.
	This also invalidates pending reset links. Passwords require at least 8
	characters and at most 72 UTF-8 bytes; invalid password payloads return 422.

Existing session JWTs retain their configured expiry after a password change;
this does not introduce server-side revocation of already-issued sessions.
The website, tracker and backoffice login pages are not changed by this feature.

Run isolated backend tests without sending real email or changing production data:

```bash
python3 -m unittest discover -s services/api/tests -p 'test_password_reset.py' -v
```

## Incident Endpoints

- `POST /api/incidents/analyze`: upload a `.csv` file using the multipart field `file`; returns aggregate JSON only.
- `GET /api/incidents/results/report`: download the most recent aggregate report as `results.csv`.

The latest aggregate report is held in process memory. Raw rows, descriptions, and customer emails are not retained or returned.

## Supplier Endpoints

The API and seeder share the `suppliers` table in TinyDB. Supplier responses
include `id` from TinyDB's `doc_id` and a system-generated UTC `updated_at`.
Neither system field is accepted in creation or update requests.

- `POST /suppliers`: create a supplier with the required context fields; returns `201` and the created record. Invalid input returns `422`.
- `GET /suppliers`: list all suppliers, optionally filtering by `country` (`Spain` or `USA`) and `category` (one valid category). Both filters can be combined, for example `/suppliers?country=Spain&category=ats_software`.
- `GET /suppliers/{id}`: retrieve one supplier; returns `404` if it does not exist.
- `PATCH /suppliers/{id}/rate`: accept `{"monthly_rate": 350.0}`. The rate must be positive and finite. A changed rate receives a new `updated_at`; an unchanged rate preserves its timestamp.
- `PATCH /suppliers/{id}/status`: accept `{"status": "active"}` or `{"status": "suspended"}`. This does not change the rate timestamp or remove the record.
- `DELETE /suppliers/{id}`: permanently remove a supplier; returns `204` without a body. Use suspension instead to retain commercial history.

Both PATCH routes and DELETE return `404` for missing suppliers. Invalid PATCH
input or query filter values return `422`. IDs must be positive integers.

Run a single API worker: access is serialized within that process, but TinyDB
does not provide cross-process write locking. Run the seeder before starting
the API, not concurrently with writes.

## Supplier Seeder

With uv installed, run from the repository root:

```bash
uv run seed
```

This loads the 15 suppliers defined in `09-lightweight-storage/CONTEXT-nexova.md`
into the `suppliers` table in `data/suppliers.json`. Each record is validated with
Pydantic and receives a system-generated UTC `updated_at`. Existing suppliers
are matched by name and country and are neither duplicated nor overwritten.
The command prints the number of inserted records, including zero on a repeat run.

To use a different database file without changing code:

```bash
SUPPLIERS_DB_PATH=/tmp/nexova-suppliers.json uv run seed
```