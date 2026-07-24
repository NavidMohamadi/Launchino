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

# CORS: explicit allowlist for the real deployed frontend, plus a permissive
# localhost/127.0.0.1 regex kept only for continued local dev (any port, since
# Vite increments if its default is busy). Add launchino.com here once the
# custom domain is connected (see PROJECT_NOTES.md/the deployment task).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://launchino.vercel.app"],
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
