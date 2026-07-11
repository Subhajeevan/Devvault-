# Deploying DevVault (free)

DevVault is a stateful Python app (FastAPI + ChromaDB + a local embedding model),
so it needs a container host with a bit of RAM — not a serverless/static host.
The container is defined in [`Dockerfile`](Dockerfile) and runs anywhere Docker does.

**Recommended free host: Hugging Face Spaces** — no credit card, 16 GB RAM (plenty
for onnxruntime + ChromaDB), built-in secrets, and a shareable portfolio URL.

> ⚠️ **Never commit your API key.** `.env` is git-ignored. On any host, set
> `GROQ_API_KEY` as a **secret / environment variable** in the host's dashboard.

> ℹ️ **Persistence:** free tiers use ephemeral disk, so the vault (ingested
> sources) resets on rebuild/restart. That's fine for a demo. Add a paid
> persistent volume mounted at `/app/data` if you want it to survive restarts.

---

## Option A — Hugging Face Spaces (recommended)

1. **Create a free account** at https://huggingface.co (no card).
2. **New Space:** https://huggingface.co/new-space
   - Owner: you · Space name: `devvault`
   - **Space SDK: `Docker`** → **Blank**
   - Hardware: **CPU basic (free)** · Visibility: Public (or Private)
3. **Add your key as a secret:** open the Space → **Settings** →
   **Variables and secrets** → **New secret**
   - Name: `GROQ_API_KEY` · Value: your `gsk_...` key
4. **Push the code.** The Space is a git repo. From this project folder:
   ```bash
   git init                       # if not already a repo
   git add -A && git commit -m "DevVault"
   # Use the HF frontmatter as the Space's README:
   cp README-HF.md README.md && git add README.md && git commit -m "HF Space config"
   git remote add space https://huggingface.co/spaces/<your-username>/devvault
   git push space main            # username = HF user, password = an HF access token
   ```
   Create the access token at https://huggingface.co/settings/tokens (role: **Write**).
5. The Space builds the Dockerfile (~3–5 min, downloads the model once) and goes
   live at `https://<your-username>-devvault.hf.space`. Done. 🎉

---

## Option B — Render (Docker)

1. Push this project to a **GitHub** repo.
2. Create a free account at https://render.com → **New → Web Service** → connect the repo.
3. Render auto-detects the `Dockerfile`. Instance type: **Free**.
4. **Environment → Add Environment Variable:** `GROQ_API_KEY = gsk_...`
5. Deploy. URL: `https://devvault-xxxx.onrender.com`.

⚠️ Render's free tier has **512 MB RAM** (onnxruntime + ChromaDB may be tight — it
can OOM on cold start) and **spins down after 15 min idle** (slow first request).
Hugging Face Spaces is the smoother free experience for this app.

---

## Other Docker hosts

The same `Dockerfile` works on **Fly.io**, **Railway**, **Koyeb**, and **Google
Cloud Run**. Each: point it at the repo/Dockerfile, set `GROQ_API_KEY`, deploy.
The app listens on `$PORT` (defaults to `7860`).

## Local Docker test (optional)

```bash
docker build -t devvault .
docker run -p 7860:7860 -e GROQ_API_KEY=gsk_your_key devvault
# open http://localhost:7860
```
