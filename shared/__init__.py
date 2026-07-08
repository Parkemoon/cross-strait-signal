# Top-level package for code shared between api/ (FastAPI routes) and
# scraper/ (pipeline). Neither side may import from the other without
# inverting the project's layering, so cross-cutting constants and pure
# helpers live here (CODE_REVIEW_2026-07-03 §4.4).
