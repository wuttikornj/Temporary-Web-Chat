"""Serves the two demo pages.

These are a working reference implementation, not the final product. The
embeddable widget (Phase 11) and the real admin dashboard (Phase 12) replace
them. They exist now so the API can be exercised by a human instead of curl.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

STATIC = Path(__file__).resolve().parent.parent / "static"

router = APIRouter(include_in_schema=False)


@router.get("/chat/{token}")
async def chat_page(token: str) -> FileResponse:
    """The doctor's view. The token stays in the URL; the page reads it from
    the address bar and never needs it injected server-side."""
    return FileResponse(STATIC / "chat.html")


@router.get("/admin")
async def admin_page() -> FileResponse:
    return FileResponse(STATIC / "admin.html")
