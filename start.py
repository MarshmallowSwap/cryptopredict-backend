#!/usr/bin/env python3
"""Recovery entrypoint: API only. No scheduler, accrual or signing jobs.

Keep this release read-only until reconciliation and monetary tests are complete.
The localhost bind is intended for the existing local reverse proxy, not direct
public exposure. This does not change an already running VPS process.
"""
import uvicorn
from app.main import app

if __name__ == "__main__":
    uvicorn.run("start:app", host="127.0.0.1", port=8000, reload=False, workers=1)
