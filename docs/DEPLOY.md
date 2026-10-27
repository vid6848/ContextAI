# Deploying ContextAI

ContextAI ships as one Docker image: a Node stage builds the React app and the Python stage serves it
together with the API. Any host that runs a Dockerfile works. The free path below is **Hugging Face
Spaces** (2 vCPU, 16 GB RAM) with data in **Supabase**, so nothing is lost when the container restarts.

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
4. Sign-in:
   - **Email links** work out of the box.
   - **Google**: in Google Cloud Console create an OAuth client (type *Web application*) with the redirect
     URI `https://<project-ref>.supabase.co/auth/v1/callback`, then enable Google under
     Authentication → Sign In / Providers and paste the client ID and secret.
   - Authentication → URL Configuration: set **Site URL** to your app's URL and add
     `<your app URL>/**` (plus `http://localhost:8000/**` and `http://localhost:5173/**` for local use)
     to **Redirect URLs**.

## 2. Push notification keys

```bash
python -m scripts.generate_vapid_keys
```

Save the two printed lines as secrets. Without fixed keys, each new container generates its own and
browsers that subscribed earlier stop receiving reminders.

## 3. Hugging Face Space

1. Create a [Hugging Face](https://huggingface.co) account, then **New Space**: SDK **Docker**,
   template **Blank**, hardware **CPU basic (free)**. Name it e.g. `contextai`.
2. In the Space's **Settings → Variables and secrets**, add as **secrets**:

   | Secret | Notes |
   |---|---|
   | `GEMINI_API_KEY` | required |
   | `DATABASE_URL` | from step 1 |
   | `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` | from step 1 (omit both for guest-only mode) |
   | `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` | from step 2 |
   | `VAPID_CONTACT` | `mailto:you@example.com` |
   | `OPENWEATHER_API_KEY`, `TAVILY_API_KEY` | optional tools |

3. Create a Hugging Face **access token** with *write* permission (Settings → Access Tokens).
4. In the GitHub repo, **Settings → Secrets and variables → Actions**:
   - secret `HF_TOKEN` = that token
   - variable `HF_SPACE` = `<your-hf-username>/contextai`
5. Push to `main` (or run the *Deploy to Hugging Face Spaces* workflow by hand). After CI passes, the
   workflow pushes a snapshot of the repo to the Space, which builds the image (about 10 minutes the
   first time) and serves it at `https://<your-hf-username>-contextai.hf.space`.
6. Add that URL to Supabase's Site URL / Redirect URLs (step 1.4).

Free Spaces sleep after about 48 hours without visitors and wake on the next request (about a minute).

## Other hosts

- **Railway**: `railway.json` builds the Dockerfile and health-checks `/health`. Set the same environment
  variables. With `DATABASE_URL` set no volume is needed.
- **Anything else** (Render, Fly.io, Cloud Run, a VM): build the Dockerfile, expose port 8000 (or set
  `PORT`), and set the environment variables above.

## Checking a deployment

- `GET /health` → `{"status": "ok"}`
- `GET /api/v1/config` → shows the Supabase URL when sign-in is configured
- Open the app, send a message, then restart the container: the chat should still be there.
