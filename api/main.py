from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

import api  # noqa: F401  (ensures src/ is on sys.path before any src import below)
from api.database import bootstrap
from api.rate_limit import limiter
from api.routers import (
    admin, admin_reports, admin_review, admin_tasks, candidates, companies, fit_dictionary, matches, reference,
    vacancies,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap()
    yield


app = FastAPI(
    title="SHEXON Talent Fit MVP API",
    description=(
        "REST layer over the deterministic matching library in src/. "
        "Not a validated employment assessment, an autonomous hiring system, or legal advice."
    ),
    version="1.2.1",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS: explicit allowlist for the real deployed frontends, plus a permissive
# localhost/127.0.0.1 regex kept only for continued local dev (any port, since
# Vite increments if its default is busy).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://launchino.vercel.app",
        "https://launchino.com",
        "https://www.launchino.com",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(candidates.router)
app.include_router(vacancies.router)
app.include_router(matches.router)
app.include_router(matches.match_run_router)
app.include_router(fit_dictionary.router)
app.include_router(companies.router)
app.include_router(admin.router)
app.include_router(admin_reports.router)
app.include_router(admin_review.router)
app.include_router(admin_tasks.router)
app.include_router(reference.router)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}
