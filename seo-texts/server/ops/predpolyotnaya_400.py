# -*- coding: utf-8 -*-
"""Предполётная перед партией: чужие прогоны, очередь, кандидаты, баланс."""
import glob
import io
import os
import re
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, r"C:\sender")

print("=== ЖИВЫЕ ПРОГОНЫ ГЕНЕРАЦИИ ===")
r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "Select-Object ProcessId, CreationDate, CommandLine | "
                    "Format-List"], capture_output=True, text=True, timeout=90)
живых = 0
for блок in (r.stdout or "").split("ProcessId"):
    if "partiya_gen" in блок or "peregen" in блок:
        живых += 1
        print("   %s" % " ".join(блок.split())[:200])
print("   прогонов генерации в процессах: %d" % живых)

print("\n=== ПОСЛЕДНИЕ ЛОГИ ПАРТИЙ ===")
логи = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"),
              key=os.path.getmtime, reverse=True)[:5]
for п in логи:
    возраст = (time.time() - os.path.getmtime(п)) / 3600.0
    первые = ""
    try:
        with io.open(п, encoding="utf-8", errors="replace") as f:
            строки = [с.strip() for с in f.readlines()[:6] if с.strip()]
        первые = " | ".join(строки)[:150]
    except OSError:
        pass
    print("   %-52s %6.1f ч назад  %8d Б" % (os.path.basename(п), возраст,
                                             os.path.getsize(п)))
    if первые:
        print("        %s" % первые)

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
print("\n=== ОЧЕРЕДЬ СЕЙЧАС ===")
for r_ in c.execute("SELECT campaign_id, status, COUNT(*) n FROM confirm_reviews"
                    " GROUP BY campaign_id, status ORDER BY campaign_id, n DESC"):
    print("   кампания %-4s %-14s %6d" % r_)
print("\n   письма за последние сутки:")
for r_ in c.execute("SELECT campaign_id, COUNT(*) n FROM confirm_reviews"
                    " WHERE created_at >= datetime('now','-1 day')"
                    " GROUP BY campaign_id"):
    print("      кампания %s: %d" % r_)
c.close()

print("\n=== СКОЛЬКО КЦ-КАНДИДАТОВ ОСТАЛОСЬ ===")
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402
from sender.ai_quota import AiQuota                           # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(r"C:\sender\sender.db")
q = AiQuota(st, db_path=r"C:\sender\sender.db", config=cfg)
try:
    print("   candidates_left(10) = %d" % q.candidates_left(10))
except Exception as e:                                        # noqa: BLE001
    print("   не посчитать: %s" % e)

print("\n=== ПРОВАЙДЕР ЖИВ? ===")
import gen_provider                                           # noqa: E402
т0 = time.time()
try:
    кл = gen_provider.make_client()
    от = gen_provider.call(кл, "Ответь одним словом: готов",
                           model="claude-sonnet-4-6", max_tokens=16)
    print("   ответ за %.1f с: %r" % (time.time() - т0, str(от)[:60]))
except Exception as e:                                        # noqa: BLE001
    print("   ПРОВАЙДЕР НЕ ОТВЕТИЛ: %s: %s" % (type(e).__name__, str(e)[:160]))

print("\n=== ИТОГ ===")
print("прогонов генерации живых: %d (если не ноль — не запускать второй)" % живых)
