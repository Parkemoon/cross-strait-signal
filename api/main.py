from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import articles, stats, notes, social
from api.routes.review import router as review_router

app = FastAPI(
    title="Cross-Strait Signal API",
    description="OSINT dashboard monitoring cross-strait dynamics through bilingual media analysis",
    version="0.1.0"
)

# Allow the React frontend to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register route modules
app.include_router(articles.router)
app.include_router(stats.router)
app.include_router(notes.router)
app.include_router(review_router)
app.include_router(social.router)

@app.get("/")
def root():
    return {"status": "ok", "name": "Cross-Strait Signal API"}