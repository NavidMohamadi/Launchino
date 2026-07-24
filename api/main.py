from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import api  # noqa: F401  (ensures src/ is on sys.path before any src import below)
from api.database import bootstrap
from api.routers import admin, admin_reports, admin_review, candidates, companies, fit_dictionary, matches, vacancies


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

# Local-dev-only CORS for frontend/ (Vite dev server, default port 5173, but
# Vite increments if that's busy -- allow any localhost/127.0.0.1 port rather
# than hardcode one). This is not a deployment configuration; boundary for
# this build is explicitly local-only (see PROJECT_NOTES.md/the frontend
# task) -- tighten to an explicit origin allowlist before any real hosting.
app.add_middleware(
    CORSMiddleware,
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


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}
