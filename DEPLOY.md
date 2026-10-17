# Deployment Guide — Tremor (Free)

## Architecture

```
Browser → Netlify (frontend/explorer.html)
              ↓ API calls
        Railway.app (src/mcp_server.py FastAPI)
              ↓
        Railway Redis add-on (FalkorDB)
              ↓
        Google Gemini API (free tier)
```

---

## Option A: Railway (Backend + FalkorDB) + Netlify (Frontend)

### Step 1: Deploy FalkorDB on Railway

1. Go to https://railway.app and sign up (free)
2. New Project → Add Service → Database → Redis
3. Note the `REDIS_URL` from the service settings
4. In Redis service settings, add variable:
   ```
   PROTECTED_MODE=no
   ```

### Step 2: Deploy Backend on Railway

1. In the same Railway project → New Service → GitHub Repo
2. Select this repo
3. Railway auto-detects `Dockerfile` and builds it
4. Add environment variables in Railway dashboard:
   ```
   GEMINI_API_KEY=your_key_here
   FALKORDB_HOST=<your-redis-service>.railway.internal
   FALKORDB_PORT=6379
   FALKORDB_GRAPH=tremor
   ```
5. The service URL will be something like: `https://tremor-production.up.railway.app`

### Step 3: Load Graph Data

After backend deploys, run the loader once to populate the graph:
```bash
# SSH into railway OR run locally with FALKORDB pointing to railway
FALKORDB_HOST=<your-redis-host>.railway.app \
FALKORDB_PORT=<port> \
REPO_PATH=./data/click \
python src/loader.py
```

Or use Railway CLI:
```bash
railway run python src/loader.py
```

### Step 4: Deploy Frontend on Netlify

1. Go to https://netlify.com and sign up (free)
2. New site → Deploy manually → drag `frontend/` folder
3. OR connect GitHub and set `frontend/` as publish directory

**Before deploying, update the API URL in `explorer.html`:**
```html
<!-- Find this line in explorer.html -->
const API = window.TREMOR_API || 'http://localhost:8765';
```

Replace with:
```html
const API = window.TREMOR_API || 'https://your-railway-url.railway.app';
```

Or create `frontend/config.js`:
```js
window.TREMOR_API = 'https://your-railway-url.railway.app';
```

And add `<script src="config.js"></script>` to `explorer.html`.

### Step 5: Configure CORS

Ensure the backend allows your Netlify domain.
The `mcp_server.py` already has `allow_origins=["*"]` for demo purposes.

For production, update to:
```python
allow_origins=["https://your-site.netlify.app"]
```

---

## Option B: Render.com (Simplest Free Deploy)

### Deploy Backend on Render

1. Go to https://render.com
2. New → Web Service → Connect GitHub repo
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `python src/mcp_server.py`
5. Add env vars: `GEMINI_API_KEY`, `FALKORDB_HOST`, `FALKORDB_PORT`

### Deploy FalkorDB on Render

1. New → Redis → Free tier
2. Note the connection details
3. Update FALKORDB_HOST in the web service env vars

---

## Option C: Local Demo (for Judges)

For hackathon submission, local works fine if you include:
- `docker-compose.yml` (already exists)
- `run-multilang-demo.sh` (already exists)
- Clear setup instructions in README

```bash
# One command to start everything locally
docker compose up -d
source .venv/bin/activate
python src/loader.py
python src/mcp_server.py &
open frontend/explorer.html
```

---

## Environment Variables Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google AI Studio API key | required |
| `GEMINI_MODEL` | Gemini model ID | `gemini-3.5-flash` |
| `FALKORDB_HOST` | FalkorDB host | `localhost` |
| `FALKORDB_PORT` | FalkorDB port | `6379` |
| `FALKORDB_GRAPH` | Graph name | `tremor` |
| `MCP_BASE_URL` | Backend URL (for agent.py) | `http://localhost:8765` |
| `REPO_PATH` | Path to repo to analyze | `./data/click` |

---

## Health Check

Once deployed, verify:
```bash
curl https://your-backend-url.railway.app/
# Expected: {"status": "ok", "functions_in_graph": 590}

curl https://your-backend-url.railway.app/tools
# Expected: {"tools": [...], "total": 5}
```

---

## Cost Estimate (Free Tier Limits)

| Service | Free Tier | Enough For? |
|---------|-----------|-------------|
| Railway | $5 credit/month | ✅ Demo |
| Netlify | 100GB bandwidth | ✅ Demo |
| Gemini API | 60 req/min | ✅ Demo |
| FalkorDB (Redis) | 25MB memory | ✅ click repo |

Total: **$0**
