"""
Anti-virus hook. ClamAV over the clamd INSTREAM protocol when CLAMAV_HOST is set;
'unavailable' otherwise. Production refuses uploads that could not be scanned
(config.verify_production_safety requires CLAMAV_HOST); development records the gap.
"""
from __future__ import annotations

import socket
import struct

from app.core.config import settings

CLEAN, INFECTED, UNAVAILABLE = "clean", "infected", "unavailable"


def scan(data: bytes) -> tuple[str, str | None]:
    """Return (status, signature_or_error)."""
    if not settings.CLAMAV_HOST:
        return UNAVAILABLE, "clamav_not_configured"
    try:
        with socket.create_connection((settings.CLAMAV_HOST, settings.CLAMAV_PORT), timeout=20) as s:
            s.sendall(b"zINSTREAM\0")
            view = memoryview(data)
            for i in range(0, len(view), 65536):
                chunk = view[i : i + 65536]
                s.sendall(struct.pack("!L", len(chunk)) + chunk.tobytes())
            s.sendall(struct.pack("!L", 0))
            reply = b""
            while not reply.endswith(b"\0"):
                part = s.recv(4096)
                if not part:
                    break
                reply += part
        text = reply.decode(errors="replace").strip("\0").strip()
        if text.endswith("OK"):
            return CLEAN, None
        if "FOUND" in text:
            return INFECTED, text.split(":", 1)[-1].replace("FOUND", "").strip()
        return UNAVAILABLE, text[:200]
    except OSError as e:
        return UNAVAILABLE, f"{type(e).__name__}: {e}"[:200]
