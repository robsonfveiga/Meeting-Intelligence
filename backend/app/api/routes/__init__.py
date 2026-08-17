"""The API surface, assembled in one place.

Prefixes and tags live here rather than on each individual route, so the shape
of the whole surface is readable on one screen and the resource modules stay
free of repeated path prefixes.
"""

from fastapi import APIRouter

from app.api.routes import chat, facts, health, jobs, meetings, search

router = APIRouter()

router.include_router(health.router, tags=["health"])
router.include_router(meetings.router, prefix="/meetings", tags=["meetings"])
router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
router.include_router(facts.router, prefix="/facts", tags=["facts"])
router.include_router(search.router, prefix="/search", tags=["search"])
router.include_router(chat.router, prefix="/chat", tags=["chat"])
