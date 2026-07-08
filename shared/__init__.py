# Top-level package for code shared between api/ (FastAPI routes) and
# scraper/ (pipeline). Neither side may import from the other without
# inverting the project's layering, so cross-cutting constants and pure
# helpers live here.
