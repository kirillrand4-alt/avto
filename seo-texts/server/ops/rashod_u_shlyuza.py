# -*- coding: utf-8 -*-
"""Спросить у шлюза, сколько потрачено — а не считать по своим прикидкам."""
import json
import os
import urllib.request

БАЗА = os.environ.get("PROVIDER_BASE_URL", "https://router.cheap").rstrip("/")
КЛЮЧ = os.environ.get("PROVIDER_API_KEY", "")
ПУТИ = ("/api/user/self", "/api/usage", "/v1/usage", "/api/log/self",
        "/api/token/", "/api/user/dashboard", "/dashboard/billing/usage",
        "/v1/dashboard/billing/usage", "/api/status")
for путь in ПУТИ:
    try:
        r = urllib.request.Request(БАЗА + путь, headers={
            "x-api-key": КЛЮЧ, "authorization": f"Bearer {КЛЮЧ}",
            "anthropic-version": "2023-06-01", "User-Agent": "curl/8.5.0"})
        with urllib.request.urlopen(r, timeout=25) as o:
            т = o.read(4000).decode("utf-8", "replace")
        print(f"\n{путь}: HTTP {o.status}")
        print("  " + т[:600])
    except Exception as ex:                                      # noqa: BLE001
        print(f"{путь}: {type(ex).__name__} {str(ex)[:90]}")
