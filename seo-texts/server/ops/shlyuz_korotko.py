# -*- coding: utf-8 -*-
"""Короткий замер шлюза без ретраев: один HTTP-вызов с жёстким таймаутом."""
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, r"C:\sender")

# 1. глушим застрявший блок
r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "Where-Object { $_.CommandLine -like '*partiya_gen*' } | "
                    "ForEach-Object { $i=$_.ProcessId; Stop-Process -Id $i -Force; \"убит $i\" }"],
                   capture_output=True, text=True, timeout=120)
print("остановка блока: %s" % ((r.stdout or "").strip() or "нечего"))

# 2. один прямой вызов к шлюзу, без обёрток и ретраев
база = os.environ.get("PROVIDER_BASE_URL", "https://router.cheap").rstrip("/")
ключ = os.environ.get("PROVIDER_API_KEY", "")
print("\nшлюз: %s, ключ: %s" % (база, "есть" if ключ else "НЕТ"))
тело = json.dumps({"model": "claude-sonnet-4-6", "max_tokens": 16,
                   "messages": [{"role": "user", "content": "скажи: готов"}]}
                  ).encode("utf-8")
з = urllib.request.Request(база + "/v1/messages", data=тело, method="POST")
з.add_header("content-type", "application/json")
з.add_header("x-api-key", ключ)
з.add_header("anthropic-version", "2023-06-01")
з.add_header("User-Agent", "curl/8.5.0")
т0 = time.time()
try:
    with urllib.request.urlopen(з, timeout=45) as о:
        d = json.loads(о.read().decode("utf-8", "replace"))
    текст = ""
    for кус in (d.get("content") or []):
        if кус.get("type") == "text":
            текст += кус.get("text") or ""
    print("   ОТВЕТ за %.1f с: %r" % (time.time() - т0, текст[:60]))
    print("   расход: %s" % json.dumps(d.get("usage") or {}, ensure_ascii=False))
except Exception as e:                                        # noqa: BLE001
    print("   ОШИБКА за %.1f с: %s: %s"
          % (time.time() - т0, type(e).__name__, str(e)[:160]))

# 3. баланс, если шлюз его отдаёт
for путь in ("/api/user/self", "/v1/dashboard/billing/subscription"):
    з2 = urllib.request.Request(база + путь)
    з2.add_header("x-api-key", ключ)
    з2.add_header("Authorization", "Bearer " + ключ)
    з2.add_header("User-Agent", "curl/8.5.0")
    try:
        with urllib.request.urlopen(з2, timeout=20) as о:
            print("   %s → %s" % (путь, о.read().decode("utf-8",
                                                        "replace")[:200]))
    except Exception as e:                                    # noqa: BLE001
        print("   %s → %s" % (путь, str(e)[:80]))

print("\n=== ИТОГ ===")
print("если один прямой вызов проходит, а линза висит — дело в модели гейта")
print("или в стриминге, а не в шлюзе целиком.")
