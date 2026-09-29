#!/usr/bin/env python3
"""Recovery webhook: authenticate deliveries but NEVER execute a deployment.

The former public default secret is removed. Rotation of the live webhook secret
and deployment of this file must be performed separately by the operator.
"""
import hashlib
import hmac
import os
import re
from fastapi import FastAPI, HTTPException, Request
import uvicorn

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


def secret_is_configured() -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{48,256}", WEBHOOK_SECRET))


def verify_signature(payload: bytes, signature: str) -> bool:
    if not secret_is_configured() or not re.fullmatch(r"sha256=[0-9a-f]{64}", signature):
        return False
    expected = "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.post("/webhook/github", status_code=202)
async def github_webhook(request: Request):
    if not secret_is_configured():
        raise HTTPException(503, "Webhook recovery access is not configured")
    # Bound request consumption even if Content-Length is missing or incorrect.
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 1_048_576:
            raise HTTPException(413, "Webhook payload too large")
        chunks.append(chunk)
    body = b"".join(chunks)
    if not verify_signature(body, request.headers.get("X-Hub-Signature-256", "")):
        raise HTTPException(401, "Invalid signature")
    return {"status": "deployment_disabled", "mode": "recovery-read-only",
            "reason": "Manual staging validation is required; no command executed"}


@app.get("/webhook/health")
async def health():
    return {"status": "alive", "service": "github-webhook", "auto_deploy_enabled": False}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9000)
