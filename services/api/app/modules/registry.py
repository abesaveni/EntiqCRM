"""
Module registry — reads the SAME manifests.json the frontend uses (packages/modules/manifests.json).
One file, two consumers; a module that is not in it does not exist to the platform.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import settings

BASE_BUNDLE: tuple[str, ...] = ("hq", "crm")
# Reserved for services the platform provisions itself. EnTIQ's own subscription billing is the
# spine (Practice HQ + billing_service), not a module, so nothing sits here today.
PLATFORM_SERVICES: tuple[str, ...] = ()


@lru_cache(maxsize=1)
def _load() -> dict[str, dict[str, Any]]:
    path = Path(settings.MANIFESTS_PATH)
    data = json.loads(path.read_text(encoding="utf-8"))
    return {m["key"]: m for m in data}


def all_modules() -> list[dict[str, Any]]:
    return list(_load().values())


def get_module(key: str) -> dict[str, Any]:
    try:
        return _load()[key]
    except KeyError:
        raise KeyError(f"Unknown module: {key}") from None


def exists(key: str) -> bool:
    return key in _load()


def is_base(key: str) -> bool:
    return key in BASE_BUNDLE or key in PLATFORM_SERVICES


def catalogue() -> list[dict[str, Any]]:
    return [m for m in all_modules() if m["status"] != "internal"]


def purchasable(key: str) -> bool:
    m = get_module(key)
    return m["status"] not in ("internal", "planned") and not is_base(key)


def required_closure(key: str) -> list[str]:
    seen: list[str] = []

    def walk(k: str) -> None:
        for dep in get_module(k)["requires"]:
            if dep not in seen:
                seen.append(dep)
                walk(dep)

    walk(key)
    return seen
