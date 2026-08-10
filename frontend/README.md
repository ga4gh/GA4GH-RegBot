# GA4GH-RegBot web UI

This Next.js app is the primary RegBot interface. It calls the FastAPI service in
`src/api/app.py` for corpus browsing, ingest, consent checks, evidence display, and
follow-up policy questions.

## Run locally

Requires Node 20.9+ (CI uses Node 22). From the repository root, start the API after
rebuilding the corpus store:

```bash
export REGBOT_ADMIN_PASSWORD='replace-with-a-long-admin-password'
python -m src.main ingest-manifest --reset
uvicorn src.api.app:app --reload --port 8000
```

In another terminal:

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

Open <http://localhost:3000/login>. The development server proxies `/api/*` and `/health` to
`http://127.0.0.1:8000`; set `REGBOT_API_URL` before starting Next.js to use another API.

The login page offers **Continue as public user** without an account. This session retains read,
retrieval, consent-check, and chat access but cannot ingest, reset, or select a custom store.
Set `REGBOT_ALLOW_GUEST_VIEWER=0` to disable it. The default account usernames are `admin`
and `viewer` when their corresponding passwords are set; there are no built-in passwords.
The latter identifier is retained for configuration compatibility while the UI labels the
read-only role **user**.
Without `REGBOT_SESSION_SECRET`, the API generates a secure per-process secret suitable for
local development. Configure a stable 32+ character secret for production or multiple API
workers.

## Verify

```bash
npm --prefix frontend run lint
npx --prefix frontend tsc -p frontend/tsconfig.json --noEmit
npm --prefix frontend run build
```

The production build uses system fonts and does not download fonts from Google.
