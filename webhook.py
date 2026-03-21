#!/usr/bin/env python3
"""
GitHub Webhook — auto-deploy backend su ogni push al branch main
Avviato come servizio separato sulla porta 9000
"""
import hmac, hashlib, subprocess, logging, os
from fastapi import FastAPI, Request, HTTPException
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("webhook")

app = FastAPI()

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "cp-webhook-2026")
BACKEND_DIR    = "/root/cryptopredict-backend"
SERVICE_NAME   = "cryptopredict"

def verify_signature(payload: bytes, signature: str) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

@app.post("/webhook/github")
async def github_webhook(request: Request):
    body = await request.body()
    sig  = request.headers.get("X-Hub-Signature-256", "")

    if not verify_signature(body, sig):
        log.warning("Invalid webhook signature")
        raise HTTPException(401, "Invalid signature")

    event   = request.headers.get("X-GitHub-Event", "")
    payload = json.loads(body)
    branch  = payload.get("ref", "")

    log.info(f"Event: {event}, branch: {branch}")

    # Solo push al branch main
    if event != "push" or branch != "refs/heads/main":
        return {"status": "ignored", "reason": "not main branch"}

    commit = payload.get("head_commit", {}).get("message", "")[:60]
    log.info(f"Deploying: {commit}")

    try:
        # git pull
        r1 = subprocess.run(
            ["git", "-C", BACKEND_DIR, "pull", "--rebase"],
            capture_output=True, text=True, timeout=60
        )
        log.info(f"git pull: {r1.stdout.strip()}")
        if r1.returncode != 0:
            log.error(f"git pull failed: {r1.stderr}")
            raise Exception(r1.stderr)

        # pip install per nuove dipendenze
        r2 = subprocess.run(
            ["pip", "install", "-r", f"{BACKEND_DIR}/requirements.txt", "-q", "--break-system-packages"],
            capture_output=True, text=True, timeout=120
        )
        if r2.returncode != 0:
            log.warning(f"pip install warning: {r2.stderr[:200]}")

        # restart servizio
        r3 = subprocess.run(
            ["systemctl", "restart", SERVICE_NAME],
            capture_output=True, text=True, timeout=30
        )
        log.info(f"restart: {'ok' if r3.returncode == 0 else r3.stderr}")

        return {
            "status":  "deployed",
            "commit":  commit,
            "git_out": r1.stdout.strip()[:200]
        }

    except Exception as e:
        log.error(f"Deploy failed: {e}")
        raise HTTPException(500, f"Deploy failed: {str(e)}")

@app.get("/webhook/health")
async def health():
    return {"status": "ok", "service": "github-webhook"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)
