# -*- coding: utf-8 -*-
"""Счётчик расхода шлюза: снять показание сейчас (и записать в журнал).

У шлюза есть /dashboard/billing/usage с накопленным total_usage. Своих
счётчиков на пути перегенерации нет: она идёт панельным вызывателем, а он
токены не считает. Поэтому меряем как счётчик воды - показание до и после.

    python zapusk_svoego_skripta.py ops/schyotchik_shlyuza.py метка
"""
import io
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

МЕТКА = " ".join(sys.argv[1:]) or "замер"
ЖУРНАЛ = r"C:\sender\_ops\schyotchik-shlyuza.jsonl"
БАЗА = os.environ.get("PROVIDER_BASE_URL", "https://router.cheap").rstrip("/")
КЛЮЧ = os.environ.get("PROVIDER_API_KEY", "")

r = urllib.request.Request(БАЗА + "/dashboard/billing/usage", headers={
    "authorization": f"Bearer {КЛЮЧ}", "x-api-key": КЛЮЧ,
    "User-Agent": "curl/8.5.0"})
with urllib.request.urlopen(r, timeout=30) as o:
    d = json.loads(o.read().decode("utf-8", "replace"))
показание = float(d.get("total_usage") or 0)
сейчас = datetime.now(timezone.utc).isoformat()
# Показание счётчика само по себе ничего не говорит: делить надо на письма.
# Считаем строки журнала перегенерации тем же замером, чтобы «до» и «после»
# были синхронны.
писем = 0
_пж = r"C:\sender\_ops\peregeneraciya-braka.jsonl"
if os.path.exists(_пж):
    for _s in io.open(_пж, encoding="utf-8", errors="replace"):
        if _s.strip():
            писем += 1
запись = {"ts": сейчас, "метка": МЕТКА, "total_usage": показание,
          "писем_в_журнале": писем}
with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
    f.write(json.dumps(запись, ensure_ascii=False) + "\n")
    f.flush()
    os.fsync(f.fileno())
print(json.dumps(запись, ensure_ascii=False))

прошлые = []
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
        try:
            прошлые.append(json.loads(s))
        except Exception:                                        # noqa: BLE001
            pass
if len(прошлые) > 1:
    п = прошлые[-2]
    d_ = показание - float(п.get("total_usage") or 0)
    print(f"\nпрошлое показание: {п.get('total_usage')} ({п.get('метка')}, "
          f"{str(п.get('ts'))[:19]})")
    писем_д = писем - int(п.get("писем_в_журнале") or 0)
    print(f"разница: {d_:.3f} единиц счётчика, писем за это время: {писем_д}")
    print(f"  если единица = цент: ${d_/100:.2f}"
          + (f", на письмо ${d_/100/писем_д:.4f}" if писем_д > 0 else ""))
