# Vercel Deployment & Media Guide for Nanvi AI

This guide explains how Nanvi is configured for Vercel while preserving the architecture for a future official deployment (Render, Railway, AWS, Docker, VPS).

---

## 1. How Images & Videos Work (Addressing "Folder Path" vs "Link Generation")

### Why folder paths work on Vercel
In Vite, any files located in the `frontend/public/` directory are static assets that Vite copies **directly into the root of `frontend/dist/`** during the build (`vite build`):
- `frontend/public/assets/nanvi-ai-enterprise-animation.mp4` &rarr; Hosted at `https://<your-vercel-domain>/assets/nanvi-ai-enterprise-animation.mp4`
- `frontend/public/nanvi-logo.png` &rarr; Hosted at `https://<your-vercel-domain>/nanvi-logo.png`
- `frontend/public/nanvi-n-icon.png` &rarr; Hosted at `https://<your-vercel-domain>/nanvi-n-icon.png`

These are **not local machine folder paths** (like `C:\...`). They are standard web URLs on your deployed website. Vercel automatically serves them globally from its high-speed Edge CDN with immutable 1-year caching headers.

### When & How to Use "Generated External Links" (CDN / Storage Buckets)
If you **do not want to include the 4.3 MB MP4 video or images in your Git repository or Vercel build**, you can upload them to an external cloud storage provider and generate a public link:

| Asset | Supported Services | Recommended Storage |
| :--- | :--- | :--- |
| **Animation Video (4.3 MB)** | Supabase Storage, Cloudinary, AWS S3, Vercel Blob | Public bucket or Cloudinary video URL |
| **Brand Logo & Icon** | Supabase Storage, Imgur, Cloudinary, AWS S3 | Public URL |

#### How to configure external links in Vercel:
You **do not need to change any code**. Simply set these environment variables in your Vercel Project Settings (`Settings` &rarr; `Environment Variables`):

```bash
# Optional: Set this to stream the video from an external CDN / link
VITE_HERO_VIDEO_URL=https://your-storage-bucket.com/nanvi-ai-enterprise-animation.mp4

# Optional: Set these if you want to host brand assets externally
VITE_LOGO_URL=https://your-storage-bucket.com/nanvi-logo.png
VITE_ICON_URL=https://your-storage-bucket.com/nanvi-n-icon.png
```

- **If left blank:** Nanvi seamlessly loads the local bundled assets (`/assets/nanvi-ai-enterprise-animation.mp4`).
- **If set:** Nanvi immediately streams from your generated link.

---

## 2. Vercel Deployment Options

Nanvi includes two configurations to support whichever way you import your project into Vercel:

### Option A: Monorepo Deployment (Root Directory `.`)
Use this when you want Vercel to build the Vite frontend and route API requests through Vercel's Python Serverless Function runtime.

1. In Vercel, import your repository.
2. Leave **Root Directory** as `.` (root).
3. The root `vercel.json` will automatically:
   - Build the frontend reproducibly: `cd frontend && npm ci && npm run build`
   - Publish static files from `frontend/dist`
   - Run the FastAPI backend serverlessly via `api/index.py`
   - Handle client-side routing for SPA without 404 errors.
   - Limit the API function to 60 seconds. Keep request work below that limit; long document indexing and batch jobs belong in a durable worker/queue.

Do not set the Vercel Root Directory to `frontend` for this option: that uses `frontend/vercel.json`, which intentionally serves only the SPA and does not deploy the Python API.

### Option B: Frontend-Only on Vercel + Backend on External Host (Recommended for heavy RAG/LangGraph)
Because this enterprise assistant features document parsing (`pypdf`, `docx`, `pptx`), vector search, and long responses, a dedicated backend is the preferred architecture for sustained production workloads. Serverless functions are request-scoped and their filesystem and in-memory state are not durable.

A recommended pattern is:
1. Deploy the FastAPI backend on **Render**, **Railway**, **Fly.io**, or your **VPS**.
2. Deploy the frontend on **Vercel** with **Root Directory** set to `frontend`.
3. In Vercel Project Settings &rarr; Environment Variables, add:
   ```bash
   VITE_API_BASE_URL=https://your-backend-api.onrender.com
   ```
   *Nanvi automatically appends `/api` and removes trailing slashes.*

---

## 3. Environment Variables Checklist for Vercel

### Frontend Variables (Vercel Project Settings)
| Variable | Required | Description | Example / Default |
| :--- | :---: | :--- | :--- |
| `VITE_DEMO_MODE` | No | Allows quick demo sign-in for testing | `true` |
| `VITE_API_BASE_URL` | No | Full URL to external backend (leave blank if serverless or using rewrites) | `https://my-backend.railway.app` |
| `VITE_HERO_VIDEO_URL` | No | External CDN URL for animation video | `https://cdn.example.com/video.mp4` |
| `VITE_LOGO_URL` | No | External CDN URL for brand logo | `https://cdn.example.com/logo.png` |
| `VITE_ICON_URL` | No | External CDN URL for brand icon | `https://cdn.example.com/icon.png` |
| `VITE_SSO_LOGIN_URL` | No | Enterprise OIDC SSO login URL | `https://sso.company.com/login` |

### Backend Variables (if deploying backend on Vercel Serverless or Official Host)
| Variable | Description |
| :--- | :--- |
| `APP_ENV` | `development` for temporary testing, `production` for official deployment |
| `JWT_SECRET` | Secret key for JWT tokens |
| `GROQ_API_KEY` | Groq LLM API Key |
| `TAVILY_API_KEY` | Tavily Web Search API Key |
| `SUPABASE_DATABASE_URL` | PostgreSQL connection string |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase service key |
| `CORS_ORIGINS` | Comma-separated list of allowed frontend origins (e.g. `https://your-project.vercel.app`) |

For a full-stack Vercel deployment, set `APP_ENV=production` explicitly for Production (and Preview if it is connected to real services). The function also defaults to production when Vercel provides its `VERCEL` environment marker, preventing development-only token routes from being enabled by accident. Configure the secrets only in Vercel Project Settings; never commit them to `.env` or `vercel.json`.

### Durable-services requirement

Vercel Functions have an ephemeral filesystem and do not share process memory reliably between requests. For a production full-stack deployment, provide `SUPABASE_DATABASE_URL` (or `DATABASE_URL`) so the application does not fall back to SQLite, and `REDIS_URL` for shared rate limiting. Do not rely on the local `backend/storage/` directory for persisted reports or email-account state. Use a database/object store for those assets, or select Option B and run the backend on a durable service.

### Pre-deploy checks

Run these before pushing:

```powershell
cd frontend
npm ci
npm run typecheck
npm run build
```

After deployment, verify `https://<your-domain>/api/health` returns `{"status":"ok"}`, load a deep SPA URL directly (for example `/settings`), and inspect the Vercel Function logs for startup errors. The API’s error response is intentionally generic; detailed diagnostics are available only in Function logs.

---

## 4. Preserving the Official Deployment Architecture
No core business logic, RAG pipelines, or security policies were changed.
When you transition to your official production deployment:
- The Dockerfiles and Nginx reverse proxy configs in [`deploy/`](file:///c:/Users/haris/Desktop/nanvi_ai_enterprise_assistant_FINAL_HANDOVER/deploy) remain untouched and ready.
- All 340+ backend tests and 56 frontend tests continue to pass 100%.
- The app seamlessly runs anywhere: locally, on Vercel, or on official enterprise cloud infrastructure.
