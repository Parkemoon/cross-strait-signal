import os
import sys
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env into os.environ before any route/auth module reads it. Idempotent
# if the systemd unit ever switches to EnvironmentFile=.
load_dotenv()

# ADMIN_TOKEN unset means require_admin / is_admin fall back to legacy
# nginx-only mode: every caller is trusted at the app layer (write endpoints
# open, admin-only reads served without a token). Deliberate for local dev,
# but on the server it usually means a lost or unsourced .env — shout at
# startup so that failure mode can't be silent.
if not os.environ.get("ADMIN_TOKEN", "").strip():
    print(
        "\n!!! ADMIN_TOKEN is not set — app-level admin auth is DISABLED "
        "(legacy nginx-only mode). !!!\n"
        "!!! Write endpoints and admin-only reads will trust EVERY caller. "
        "If this is production, restore .env and restart. !!!\n",
        file=sys.stderr,
    )

from api.routes import articles, stats, notes, social, economy, trade_access, military, polls, diplomacy
from api.routes.review import router as review_router

app = FastAPI(
    title="Cross-Strait Signal API",
    description="OSINT dashboard monitoring cross-strait dynamics through bilingual media analysis",
    version="0.1.0"
)

# CORS allowlist. Override via CORS_ORIGINS env var as a comma-separated list
# (e.g. for local dev: "http://localhost:3000"). Default covers the two prod
# vhosts. Browsers reject credentialed requests to "*"; we use a strict list
# and do not enable credentials because the API does not rely on cookies.
_default_origins = "https://strait-signal.net,https://admin.strait-signal.net,http://localhost:3000,http://localhost:3001"
_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", _default_origins).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)

# Register route modules
app.include_router(articles.router)
app.include_router(stats.router)
app.include_router(notes.router)
app.include_router(review_router)
app.include_router(social.router)
app.include_router(economy.router)
app.include_router(trade_access.router)
app.include_router(military.router)
app.include_router(polls.router)
app.include_router(diplomacy.router)

@app.get("/")
def root():
    return {"status": "ok", "name": "Cross-Strait Signal API"}
