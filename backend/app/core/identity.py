"""Who is making this request.

INTEGRATION POINT. This repo does not know how the host application
authenticates people. It only needs, for each intake call, the verified
identity of the doctor making it.

The identity MUST come from the server-side session, never from the request
body. An email in the body is client-supplied: anyone able to reach the
endpoint could create a consult naming someone else's address, and this system
would then email that person a link to patient data.

To integrate: replace `get_current_consultee` with a dependency that reads the
host application's SSO session, and return a Consultee. Nothing else in this
codebase needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status

from app.config import Settings, get_settings


@dataclass(frozen=True)
class Consultee:
    """The authenticated requesting doctor."""

    email: str
    name: str | None = None


async def get_current_consultee(
    settings: Settings = Depends(get_settings),
    x_consultee_email: str | None = Header(default=None),
    x_consultee_name: str | None = Header(default=None),
) -> Consultee:
    """Development stub.

    Reads the identity from request headers, and ONLY when DEV_AUTH_STUB is
    switched on. With the flag off, which is the default and the only correct
    setting for a deployment, this refuses every call rather than failing open.
    An unimplemented auth dependency that returns a default identity is worse
    than one that returns 500, because nothing looks broken.
    """
    if not settings.DEV_AUTH_STUB:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Identity provider not configured. Wire "
                "app.core.identity.get_current_consultee to the host "
                "application's SSO session."
            ),
        )

    if not x_consultee_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    return Consultee(email=x_consultee_email, name=x_consultee_name)


@dataclass(frozen=True)
class Admin:
    """The authenticated resident or staff member answering from the
    dashboard. Every admin sees every station: Stations group work, they are
    not a permission boundary. See DECISIONS.md section 3."""

    email: str
    name: str | None = None


async def get_current_admin(
    settings: Settings = Depends(get_settings),
    x_admin_email: str | None = Header(default=None),
    x_admin_name: str | None = Header(default=None),
) -> Admin:
    """Development stub, replaced by real admin auth in Phase 9.

    Same rule as get_current_consultee: refuses rather than falling open when
    DEV_AUTH_STUB is off.
    """
    if not settings.DEV_AUTH_STUB:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin authentication not configured (Phase 9).",
        )

    if not x_admin_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    return Admin(email=x_admin_email, name=x_admin_name)
