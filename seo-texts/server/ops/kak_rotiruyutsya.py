# -*- coding: utf-8 -*-
"""Как ротируются мобильные прокси: файл, ссылки смены IP, код, который их крутит.

Секреты не печатаем: логины и токены маскируем, ссылки показываем без
хвоста с ключом.
"""
import io
import os
import re

ФАЙЛЫ = [r"C:\sender\proxies-mobile.txt",
         r"C:\seostat\drop\zenno\proxy_mobile.txt",
         r"C:\sender\_tmp\pereobhod-mobile.json"]


def маска(с):
    с = str(с or "")
    return (с[:2] + "***" + с[-2:]) if len(с) > 5 else "***"


def безопасно(с):
    """Прячем то, что похоже на ключ, оставляя видимой структуру."""
    с = re.sub(r"([?&](?:key|token|api_key|apikey|pass|password)=)[^&\s]+",
               r"\1<скрыто>", с, flags=re.I)
    с = re.sub(r"://([^:/@\s]+):([^@\s]+)@", lambda m: "://%s:<скрыто>@"
               % маска(m.group(1)), с)
    return с


print("=== ФАЙЛЫ МОБИЛЬНЫХ ===")
for ф in ФАЙЛЫ:
    if not os.path.exists(ф):
        print("   %s — НЕТ" % ф)
        continue
    т = io.open(ф, encoding="utf-8", errors="replace").read()
    print("   %s — %d байт, строк %d"
          % (ф, len(т), len(т.splitlines())))
    for l in т.splitlines()[:14]:
        if l.strip():
            print("      " + безопасно(l.strip())[:150])

print("")
print("=== ССЫЛКИ СМЕНЫ IP В КОДЕ И КОНФИГАХ ===")
образцы = re.compile(
    r"(rotate|changeip|change_ip|newip|new_ip|reset.?ip|смена.?ip|ротац)",
    re.I)
найдено = 0
for корень in (r"C:\sender", r"C:\seostat\drop"):
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("__pycache__", ".git", ".venv",
                                              "node_modules", "drop-storage")]
        for имя in файлы:
            if not имя.endswith((".py", ".txt", ".json", ".yaml", ".yml",
                                 ".env", ".cmd", ".md")):
                continue
            п = os.path.join(путь, имя)
            try:
                if os.path.getsize(п) > 400000:
                    continue
                т = io.open(п, encoding="utf-8", errors="replace").read()
            except Exception:                                  # noqa: BLE001
                continue
            for м in образцы.finditer(т):
                н = т.rfind("\n", 0, м.start()) + 1
                к = т.find("\n", м.end())
                строка = т[н:к if к > 0 else н + 160].strip()
                if len(строка) < 4 or строка.startswith("#"):
                    continue
                print("   %s:%d| %s"
                      % (п.replace("C:\\", ""), т[:м.start()].count("\n") + 1,
                         безопасно(строка)[:130]))
                найдено += 1
                break
            if найдено > 24:
                break
        if найдено > 24:
            break
if not найдено:
    print("   упоминаний ротации в коде не нашлось")
