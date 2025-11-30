# backend/app/rate_limit.py

from __future__ import annotations

from fastapi import HTTPException, Request, status
import time
from typing import Dict, List

MAX_REQUESTS = 10
WINDOW_SECONDS = 60

# { ip: [timestamps] }
REQUEST_LOG: Dict[str, List[float]] = {}


def rate_limiter(request: Request):
    """
    Naive in-memory rate limiter.
    Limits each IP to MAX_REQUESTS per WINDOW_SECONDS.
    """
    ip = request.client.host
    now = time.time()

    timestamps = REQUEST_LOG.get(ip, [])
    # keep only calls within the defined window
    timestamps = [t for t in timestamps if now - t < WINDOW_SECONDS]

    if len(timestamps) >= MAX_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again in a minute.",
        )

    timestamps.append(now)
    REQUEST_LOG[ip] = timestamps
