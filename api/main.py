import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env into os.environ before any route/auth module reads it. Idempotent
# if the systemd unit ever switches to EnvironmentFile=.
load_dotenv()

from api.routes import articles, stats, notes, social, economy, trade_access, military, polls
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

@app.get("/")
def root():
    return {"status": "ok", "name": "Cross-Strait Signal API"}
