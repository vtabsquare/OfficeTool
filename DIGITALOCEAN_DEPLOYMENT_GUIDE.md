# VTAB Office Tool — DigitalOcean Deployment Guide

## Architecture Overview

Your project has **3 services** that must be deployed:

```
┌─────────────────────┐     REST API      ┌──────────────────────┐
│   FRONTEND (Vite)   │ ───────────────→  │  BACKEND (Flask)     │
│   Static Site       │                   │  Python + Gunicorn   │
│   Port: 80/443      │                   │  Port: 5000          │
└────────┬────────────┘                   └──────────┬───────────┘
         │                                           │
         │ WebSocket                    HTTP POST     │
         │                              /emit         │
         ▼                                           ▼
┌─────────────────────────────────────────────────────┐
│           SOCKET SERVER (Node.js)                   │
│           Express + Socket.IO                       │
│           Port: 4001                                │
└─────────────────────────────────────────────────────┘
```

### Inter-Service Communication:
- **Frontend → Backend**: REST API calls (VITE_API_BASE_URL)
- **Frontend → Socket Server**: WebSocket connection (VITE_SOCKET_URL)
- **Backend → Socket Server**: HTTP POST to /emit endpoint (SOCKET_SERVER_URL)
- **Socket Server → Backend**: HTTP calls for chat API (PY_API_BASE)

---

## Deployment Option: DigitalOcean App Platform (Recommended)

DigitalOcean App Platform supports multiple components in a single app. You'll deploy all 3 services as components of one app.

---

## STEP 1: Prepare Your Repository

### 1.1 — Push code to GitHub/GitLab

Make sure your `office_tool/` folder is the root of a Git repository pushed to GitHub or GitLab. DigitalOcean App Platform deploys from Git.

```bash
cd office_tool
git init   # if not already
git remote add origin https://github.com/YOUR_USERNAME/vtab-office-tool.git
git add .
git commit -m "Prepare for DigitalOcean deployment"
git push -u origin main
```

### 1.2 — Verify .gitignore

Your `.gitignore` already excludes secrets (`*.env`, `id.env`, `node_modules`, `dist`). This is correct. **Never commit secrets.**

---

## STEP 2: Prepare Backend for Production

### 2.1 — Create a Procfile or start command

The backend uses `gunicorn` (already in requirements.txt). The start command will be:

```
gunicorn unified_server:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

### 2.2 — Verify requirements.txt

Your `backend/requirements.txt` already has all dependencies. Add these if missing:

```
Flask==3.0.3
flask-cors==5.0.0
Flask-Mail==0.9.1
python-dotenv==1.0.1
msal==1.31.0
requests==2.32.3
PyPDF2==3.0.1
reportlab==4.0.7
xhtml2pdf==0.2.13
SQLAlchemy==2.0.36
psycopg[binary]
gunicorn==21.2.0
google-auth
google-auth-oauthlib
google-api-python-client
PyJWT>=2.0.0
```

> **Note**: `PyJWT` is imported in `unified_server.py` but not listed in requirements.txt. Add it.

### 2.3 — Environment Variables Needed for Backend

These will be set in DigitalOcean App Platform dashboard:

| Variable | Description | Example |
|---|---|---|
| `TENANT_ID` | Azure AD Tenant ID | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `CLIENT_ID` | Azure AD App Client ID | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `CLIENT_SECRET` | Azure AD App Client Secret | `your-secret` |
| `RESOURCE` | Dataverse URL | `https://yourorg.crm.dynamics.com` |
| `FLASK_ENV` | Set to production | `production` |
| `PORT` | Auto-set by DO | (auto) |
| `SOCKET_SERVER_URL` | Internal URL of socket server | `https://your-socket-app.ondigitalocean.app` |
| `FRONTEND_BASE_URL` | URL of deployed frontend | `https://your-frontend.ondigitalocean.app` |
| `MAIL_SERVER` | SMTP server | `smtp.gmail.com` |
| `MAIL_USERNAME` | Sender email | `your-email@gmail.com` |
| `MAIL_PASSWORD` | App password | `your-app-password` |
| `MAIL_DEFAULT_SENDER` | Default from address | `your-email@gmail.com` |
| `GOOGLE_CLIENT_ID` | Google OAuth Client ID | `xxxxx.apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | Google OAuth Secret | `your-google-secret` |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL | `https://your-backend.ondigitalocean.app/google/oauth2callback` |
| `GEMINI_API_KEY` | (if using AI features) | `your-key` |

---

## STEP 3: Prepare Socket Server for Production

### 3.1 — Verify package.json

Your `socket-server/package.json` already has `"start": "node single_server.js"`. This is correct.

### 3.2 — Environment Variables Needed for Socket Server

| Variable | Description | Example |
|---|---|---|
| `PORT` | Auto-set by DO | (auto) |
| `SOCKET_ORIGINS` | Allowed CORS origins (comma-separated) | `https://your-frontend.ondigitalocean.app,https://your-backend.ondigitalocean.app` |
| `PY_API_BASE` | Backend URL for chat module | `https://your-backend.ondigitalocean.app/chat` |
| `BACKEND_URL` | Backend URL for attendance module | `https://your-backend.ondigitalocean.app` |

---

## STEP 4: Prepare Frontend for Production

### 4.1 — Build Command

```
npm install && npm run build
```

Output directory: `dist`

### 4.2 — Environment Variables (Build-time)

| Variable | Description | Example |
|---|---|---|
| `VITE_API_BASE_URL` | Backend URL | `https://your-backend.ondigitalocean.app` |
| `VITE_SOCKET_URL` | Socket server URL | `https://your-socket.ondigitalocean.app` |
| `VITE_CHAT_SOCKET_URL` | Same as VITE_SOCKET_URL | `https://your-socket.ondigitalocean.app` |

---

## STEP 5: Deploy on DigitalOcean App Platform

### 5.1 — Create a New App

1. Go to [DigitalOcean App Platform](https://cloud.digitalocean.com/apps)
2. Click **"Create App"**
3. Connect your **GitHub** repository
4. Select the repository and branch (`main`)

### 5.2 — Configure Component 1: BACKEND (Python)

| Setting | Value |
|---|---|
| **Name** | `vtab-backend` |
| **Type** | Web Service |
| **Source Directory** | `/backend` |
| **Environment** | Python |
| **Build Command** | `pip install -r requirements.txt` |
| **Run Command** | `gunicorn unified_server:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120` |
| **HTTP Port** | `5000` |
| **Instance Size** | Basic ($5/mo) or Professional ($12/mo) |
| **Health Check Path** | `/ping` |

Then add all **Backend Environment Variables** from Step 2.3.

### 5.3 — Configure Component 2: SOCKET SERVER (Node.js)

| Setting | Value |
|---|---|
| **Name** | `vtab-socket` |
| **Type** | Web Service |
| **Source Directory** | `/socket-server` |
| **Environment** | Node.js |
| **Build Command** | `npm install` |
| **Run Command** | `npm start` |
| **HTTP Port** | `4001` |
| **Instance Size** | Basic ($5/mo) |
| **Health Check Path** | (leave empty — socket servers don't have a standard health endpoint) |

Then add all **Socket Server Environment Variables** from Step 3.2.

> **IMPORTANT**: DigitalOcean App Platform supports WebSocket connections natively. No extra configuration needed.

### 5.4 — Configure Component 3: FRONTEND (Static Site)

| Setting | Value |
|---|---|
| **Name** | `vtab-frontend` |
| **Type** | Static Site |
| **Source Directory** | `/` (root of office_tool) |
| **Build Command** | `npm install && npm run build` |
| **Output Directory** | `dist` |

Then add the **Frontend Environment Variables** from Step 4.2.

Add a **Catchall Route** for SPA routing:
- From: `/*`
- To: `/index.html`
- Status: `200`

---

## STEP 6: Update URLs After Deployment

After the first deploy, DigitalOcean will assign URLs like:
- Backend: `https://vtab-backend-xxxxx.ondigitalocean.app`
- Socket: `https://vtab-socket-xxxxx.ondigitalocean.app`
- Frontend: `https://vtab-frontend-xxxxx.ondigitalocean.app`

### 6.1 — Update Environment Variables (Circular Dependency Resolution)

You need to update env vars with the actual URLs:

**Backend env vars:**
```
SOCKET_SERVER_URL=https://vtab-socket-xxxxx.ondigitalocean.app
FRONTEND_BASE_URL=https://vtab-frontend-xxxxx.ondigitalocean.app
GOOGLE_REDIRECT_URI=https://vtab-backend-xxxxx.ondigitalocean.app/google/oauth2callback
```

**Socket Server env vars:**
```
SOCKET_ORIGINS=https://vtab-frontend-xxxxx.ondigitalocean.app,https://vtab-backend-xxxxx.ondigitalocean.app
PY_API_BASE=https://vtab-backend-xxxxx.ondigitalocean.app/chat
BACKEND_URL=https://vtab-backend-xxxxx.ondigitalocean.app
```

**Frontend env vars (triggers rebuild):**
```
VITE_API_BASE_URL=https://vtab-backend-xxxxx.ondigitalocean.app
VITE_SOCKET_URL=https://vtab-socket-xxxxx.ondigitalocean.app
VITE_CHAT_SOCKET_URL=https://vtab-socket-xxxxx.ondigitalocean.app
```

### 6.2 — Redeploy

After updating env vars, click **"Deploy"** again in the App Platform dashboard. All 3 components will rebuild with the correct URLs.

---

## STEP 7: Code Changes Required Before Deployment

### 7.1 — Add PyJWT to requirements.txt

`unified_server.py` imports `jwt` but it's not in requirements.txt.

### 7.2 — Remove Hardcoded Render URLs (CRITICAL)

The following files have hardcoded Render fallback URLs that should use env vars:

| File | Current Hardcoded URL | Should Be |
|---|---|---|
| `config.js` | `https://vtab-office-tool.onrender.com` | Use env var only |
| `src/socket.js` | `https://office-tool-socket.onrender.com` | Use env var only |
| `socket-server/socketManager.js` | `https://office-tool-socket.onrender.com` | Use env var only |
| `features/attendanceSocket.js` | `https://office-tool-socket.onrender.com` | Use env var only |
| `backend/chats.py` | `http://localhost:4001` | Use `SOCKET_SERVER_URL` env var |
| `backend/attendance_service_v2.py` | `https://office-tool-socket.onrender.com` | Use `SOCKET_SERVER_URL` env var |

### 7.3 — Ensure Backend Binds to 0.0.0.0

Already done in `unified_server.py` line 13137: `Host: 0.0.0.0`. ✅

### 7.4 — Ensure Socket Server Reads PORT from Environment

Already done in `single_server.js` line 217: `process.env.PORT || process.env.SOCKET_PORT || 4001`. ✅

---

## STEP 8: Custom Domain (Optional)

1. In App Platform → Settings → Domains
2. Click **"Add Domain"**
3. Enter your domain (e.g., `app.vtab.com`)
4. Add the CNAME record to your DNS provider
5. DigitalOcean auto-provisions SSL certificates

---

## STEP 9: Post-Deployment Verification Checklist

| # | Check | How |
|---|---|---|
| 1 | Backend health | Visit `https://your-backend/ping` → should return `{"message": "Backend is connected ✅"}` |
| 2 | Frontend loads | Visit frontend URL → login page should appear |
| 3 | API connection | Open browser console on frontend → no CORS errors |
| 4 | Socket connection | Open browser console → look for `[SOCKET] Connected successfully` |
| 5 | Chat socket | Open browser console → look for `[CHAT-SOCKET] connected` |
| 6 | Check-in/Check-out | Test attendance flow end-to-end |
| 7 | Meet calls | Test initiating a meet call |
| 8 | Chat messages | Send a test message |
| 9 | Google Calendar | Test Google OAuth flow |
| 10 | Email sending | Test password reset or any email feature |

---

## STEP 10: Troubleshooting

### CORS Errors
- Ensure `SOCKET_ORIGINS` includes the frontend URL
- Backend already has `CORS(app, resources={r"/api/*": {"origins": "*"}})` — this allows all origins
- For production, restrict to your frontend domain

### WebSocket Connection Failed
- DigitalOcean App Platform supports WebSockets natively
- Ensure the socket server component is a **Web Service** (not a Worker)
- Check that `VITE_SOCKET_URL` points to the correct socket server URL (with `https://`)

### 502 Bad Gateway
- Check the **Runtime Logs** in App Platform dashboard
- Usually means the app crashed on startup
- Verify all env vars are set correctly
- Check that `PORT` is being read from environment (not hardcoded)

### Dataverse Connection Failed
- Verify `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET`, `RESOURCE` are correct
- Ensure the Azure AD app registration allows the DigitalOcean server IP (or has no IP restrictions)

### Google OAuth Redirect Mismatch
- Update `GOOGLE_REDIRECT_URI` to match the deployed backend URL
- Update the redirect URI in Google Cloud Console → Credentials → OAuth 2.0 Client

---

## Cost Estimate

| Component | Type | Cost |
|---|---|---|
| Backend (Python) | Basic Instance | $5/mo |
| Socket Server (Node.js) | Basic Instance | $5/mo |
| Frontend (Static) | Static Site | **Free** (on App Platform) |
| **Total** | | **~$10/mo** |

> You can scale up to Professional instances ($12/mo each) if you need more resources.

---

## Alternative: DigitalOcean Droplet (Manual Setup)

If you prefer a single VPS instead of App Platform:

1. Create a **Droplet** (Ubuntu 22.04, $6/mo minimum)
2. SSH in and install: `Python 3.11+`, `Node.js 18+`, `Nginx`, `PM2`, `Certbot`
3. Clone your repo
4. Run backend with Gunicorn behind Nginx
5. Run socket server with PM2 behind Nginx
6. Serve frontend static files directly from Nginx
7. Configure Nginx as reverse proxy for all 3 services
8. Use Certbot for free SSL

This is more complex but gives you full control and costs less ($6/mo for everything).

---

## Summary of Deployment Order

1. ✅ Push code to GitHub
2. ✅ Make code changes (remove hardcoded URLs, add PyJWT)
3. ✅ Create DigitalOcean App with 3 components
4. ✅ Set environment variables for all 3 components
5. ✅ Deploy (first deploy will assign URLs)
6. ✅ Update env vars with actual assigned URLs
7. ✅ Redeploy
8. ✅ Verify all services are working
9. ✅ (Optional) Add custom domain
