"""Fail-closed recovery boundary. This release intentionally has no write switch."""
from hmac import compare_digest
import re
from typing import NoReturn
from urllib.parse import parse_qs

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

MODE = "recovery-read-only"
PUBLIC_PATHS = frozenset({"/", "/health", "/api/v1/system/status",
                          "/api/v1/markets", "/api/v1/markets/images/all",
                          "/api/v1/yield/stats"})
UUID = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
PUBLIC_DETAIL = re.compile(rf"/api/v1/(?:markets|yield/market)/{UUID}/?")


class RecoveryWriteDisabled(RuntimeError):
    """An unverified legacy monetary operation was deliberately quarantined."""


def block_legacy_write(operation: str) -> NoReturn:
    raise RecoveryWriteDisabled(f"{operation} disabled during recovery; no write performed")


def auth_error(scope: Scope, configured_token: str):
    """Only a fresh, header-only recovery token authorizes private reads."""
    if not configured_token:
        return 503, "Recovery administrator access is not configured"
    values = [v for k, v in scope.get("headers", []) if k.lower() == b"authorization"]
    if len(values) != 1:
        return 401, "A recovery Bearer token is required"
    scheme, separator, supplied = values[0].partition(b" ")
    if (not separator or scheme.lower() != b"bearer" or not supplied
            or len(supplied) > 256
            or not compare_digest(supplied, configured_token.encode("utf-8"))):
        return 401, "Invalid recovery authorization"
    return None


async def require_recovery_admin(request: Request) -> None:
    error = auth_error(request.scope, request.app.state.recovery_admin_token)
    if error:
        status, detail = error
        raise HTTPException(status, detail, headers={"WWW-Authenticate": "Bearer"})


class RecoveryGuard:
    """Deny mutations BEFORE parsing bodies or reaching any legacy handler.

    Public reads are explicitly allowlisted; unknown/new routes require operator
    authorization. This protects the API, not direct blockchain transactions.
    """
    def __init__(self, app: ASGIApp, admin_token: str = "") -> None:
        self.app = app
        self.admin_token = admin_token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def safe_send(message):
            if message["type"] == "http.response.start":
                controlled = {b"cache-control", b"x-cryptopredict-mode", b"x-cryptopredict-accounting"}
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() not in controlled]
                headers.extend([(b"cache-control", b"no-store"),
                                (b"x-cryptopredict-mode", MODE.encode()),
                                (b"x-cryptopredict-accounting", b"legacy-unverified")])
                message = dict(message, headers=headers)
            await send(message)

        method = scope.get("method", "").upper()
        if method not in {"GET", "HEAD", "OPTIONS"}:
            await JSONResponse({"detail": "Legacy API writes are disabled during recovery",
                                "code": "RECOVERY_READ_ONLY"}, status_code=503)(scope, receive, safe_send)
            return
        if method == "OPTIONS":
            # CORSMiddleware handles valid preflights outside this guard. Never
            # dispatch an OPTIONS handler which could have unexpected side effects.
            await Response(status_code=204)(scope, receive, safe_send)
            return
        query = parse_qs(scope.get("query_string", b"").decode("latin-1"), keep_blank_values=True)
        if {"admin_token", "access_token"}.intersection(query):
            await JSONResponse({"detail": "Credentials in URLs are not accepted; use Authorization"},
                               status_code=400)(scope, receive, safe_send)
            return
        path = scope.get("path", "")
        if path.rstrip("/") not in (PUBLIC_PATHS - {"/"}) and path != "/" and not PUBLIC_DETAIL.fullmatch(path):
            error = auth_error(scope, self.admin_token)
            if error:
                status, detail = error
                await JSONResponse({"detail": detail}, status_code=status,
                                   headers={"WWW-Authenticate": "Bearer"})(scope, receive, safe_send)
                return
        await self.app(scope, receive, safe_send)
