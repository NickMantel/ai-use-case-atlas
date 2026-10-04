"""Shared web helpers: templates, identity, redirects."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .catalog import get_catalog
from .config import get_framework, get_settings
from .models import article
from .providers import get_provider

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.filters["article"] = article

# Identity headers set by common front doors. Trust them only when the app is
# deployed behind that proxy (Databricks Apps, Google IAP, Azure Easy Auth).
IDENTITY_HEADERS = (
    "x-forwarded-email",                    # Databricks Apps
    "x-goog-authenticated-user-email",      # Google Cloud IAP: "accounts.google.com:user@x"
    "x-ms-client-principal-name",           # Azure App Service / Container Apps Easy Auth
)
NAME_COOKIE = "atlas_name"


def current_user(request: Request) -> tuple[str, bool]:
    """Returns (name, from_proxy)."""
    for header in IDENTITY_HEADERS:
        value = request.headers.get(header)
        if value:
            return value.split(":", 1)[-1], True
    name = request.cookies.get(NAME_COOKIE)
    return (name or "anonymous"), False


def _provider_status() -> dict[str, Any]:
    try:
        p = get_provider()
        return {"ok": True, "label": p.describe(), "stub": p.is_stub}
    except Exception as exc:  # misconfiguration should not take the app down
        return {"ok": False, "label": f"unavailable: {exc}", "stub": False}


def _catalog_status() -> dict[str, Any]:
    try:
        return {"ok": True, "label": get_catalog().describe()}
    except Exception as exc:
        return {"ok": False, "label": f"unavailable: {exc}"}


def render(request: Request, template: str, **ctx: Any):
    user, from_proxy = current_user(request)
    base = {
        "request": request,
        "fw": get_framework(),
        "settings": get_settings(),
        "user": user,
        "user_from_proxy": from_proxy,
        "provider": _provider_status(),
        "catalog_status": _catalog_status(),
        "msg": request.query_params.get("msg"),
        "err": request.query_params.get("err"),
    }
    return templates.TemplateResponse(request, template, {**base, **ctx})


def redirect(url: str, msg: str | None = None, err: str | None = None) -> RedirectResponse:
    sep = "&" if "?" in url else "?"
    if msg:
        url += f"{sep}msg={quote(msg)}"
        sep = "&"
    if err:
        url += f"{sep}err={quote(err[:300])}"
    return RedirectResponse(url, status_code=303)
