# Deploying ContextAI

ContextAI ships as one Docker image: a Node stage builds the React app and the Python stage serves it
together with the API. Any host that runs a Dockerfile works. The free path below is **Render** (free web
service, 512 MB RAM) with data in **Supabase**, so nothing is lost when the container restarts.

## 1. Database and sign-in (Supabase)

1. Create a project at [supabase.com](https://supabase.com) (any region close to your users).
2. Collect three values:
   | Variable | Where |
   |---|---|
   | `SUPABASE_URL` | Connect (top bar) or Project Settings → Data API → Project URL |
   | `SUPABASE_PUBLISHABLE_KEY` | Project Settings → API Keys → publishable key (`sb_publishable_…`) |
   | `DATABASE_URL` | Connect → Connection String → **Session pooler**, with your database password filled in |

   Never use the **secret** key (`sb_secret_…`); ContextAI doesn't need it.
3. Tables are created automatically on the first start (`src/backend/db/schema.sql`). Row-level security
   is on with no policies, so Supabase's public API can't read them; only the server's connection can.
4. Set up sign-in under **Authentication**:
   - **URL Configuration**: set **Site URL** to your app's URL and add `<your app URL>/**` (plus
     `http://localhost:8000/**` and `http://localhost:5173/**` for local use) to **Redirect URLs**.
   - **Sign In / Providers → Email**: turn off **Confirm email**, so email and password accounts work
     straight away without sending any mail.
   - **Sign In / Providers → Google**: in [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
     create an OAuth client (type **Web application**) with the callback URL Supabase shows as its authorized
     redirect URI, then paste the client ID and secret into Supabase and enable the provider. The **Continue
     with Google** button appears in the app once this is on.

## 2. Push notification keys

```bash
python -m scripts.generate_vapid_keys
```

Save the two printed lines as secrets. Without fixed keys, each new container generates its own and
browsers that subscribed earlier stop receiving reminders.

## 3. Render

1. Sign up at [render.com](https://render.com) with GitHub, then **New → Web Service** and pick this repo.
   Runtime **Docker**, instance type **Free**.
2. Under **Environment**, add:

   | Variable | Notes |
   |---|---|
   | `GEMINI_API_KEY` | required |
   | `DATABASE_URL` | from step 1 |
   | `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` | from step 1 (omit both for guest-only mode) |
   | `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` | from step 2 |
   | `VAPID_CONTACT` | `mailto:you@example.com` |
   | `OPENWEATHER_API_KEY`, `TAVILY_API_KEY` | optional tools |
   | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | optional: trace every chat turn in [Langfuse](https://cloud.langfuse.com) |

3. Set **Health Check Path** to `/health` and deploy. Render builds the image and serves it at
   `https://<service-name>.onrender.com`, then redeploys on every push to `main`.
4. Add that URL to Supabase's Site URL / Redirect URLs (step 1.4).

Free services sleep after about 15 minutes without visitors and wake on the next request (about a minute).

## Other hosts

- **Railway**: `railway.json` builds the Dockerfile and health-checks `/health`. Set the same environment
  variables. With `DATABASE_URL` set no volume is needed.
- **Anything else** (Hugging Face Spaces, Fly.io, Cloud Run, a VM): build the Dockerfile, expose port 8000 (or set
  `PORT`), and set the environment variables above.

## Checking a deployment

- `GET /health` → `{"status": "ok"}`
- `GET /api/v1/config` → shows the Supabase URL when sign-in is configured
- Open the app, send a message, then restart the container: the chat should still be there.
