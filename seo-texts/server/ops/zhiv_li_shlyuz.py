# -*- coding: utf-8 -*-
"""Жив ли провайдерский шлюз с этого сервера: один короткий вызов + сеть."""
import os
import socket
import ssl
import sys
import time

sys.path.insert(0, r"C:\sender")
база = os.environ.get("PROVIDER_BASE_URL", "https://router.cheap")
хост = база.split("//", 1)[-1].split("/")[0]
print("шлюз: %s" % хост)
t = time.time()
try:
    s = socket.create_connection((хост, 443), timeout=10)
    кс = ssl.create_default_context().wrap_socket(s, server_hostname=хост)
    print("TCP+TLS: ок за %.1f с, %s" % (time.time() - t, кс.version()))
    кс.close()
except Exception as e:  # noqa: BLE001
    print("TCP+TLS: СБОЙ за %.1f с: %s" % (time.time() - t, e))

import gen_provider  # noqa: E402
for модель in ("claude-sonnet-4-6", "claude-opus-4-8"):
    t = time.time()
    try:
        кл = gen_provider.make_client()
        ответ = gen_provider.call(
            кл, [{"role": "user", "content": "Ответь одним словом: работает?"}],
            model=модель, attempts=1, thinking=False)
        текст = ответ if isinstance(ответ, str) else str(getattr(ответ, "text", ответ))
        print("%-20s ок за %.1f с: %s" % (модель, time.time() - t, текст[:60]))
    except Exception as e:  # noqa: BLE001
        print("%-20s СБОЙ за %.1f с: %s" % (модель, time.time() - t, str(e)[:160]))
print("=== ШЛЮЗ ===")
