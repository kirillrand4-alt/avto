# -*- coding: utf-8 -*-
"""Два вопроса владельца: работает ли работник проб и правда ли идут письма.

1. РАБОТНИК. Он живёт на ВПС и берёт адреса из очереди на проверку. Смотрим
   не «запущен ли», а результат: сколько вердиктов прибавилось за сутки, что
   с загруженными 24.08 компаниями и когда была последняя проба.
2. ГЕНЕРАЦИЯ. «Процесс жив» - не доказательство. Доказательство - письма в
   очереди подтверждения и строки в журнале прогона.
"""
import glob
import io
import json
import os
import sqlite3
import time
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("=== 1. РАБОТНИК ПРОБ ===")
все = c.execute("SELECT COUNT(*) FROM addr_probe").fetchone()[0]
сегодня = c.execute("SELECT COUNT(*) FROM addr_probe WHERE substr(ts,1,10)="
                    "'2026-08-24'").fetchone()[0]
вчера = c.execute("SELECT COUNT(*) FROM addr_probe WHERE substr(ts,1,10)="
                  "'2026-08-23'").fetchone()[0]
print(f"вердиктов всего {все}; за 23.08 {вчера}; за 24.08 {сегодня}")
посл = c.execute("SELECT email, verdict, source, ts FROM addr_probe "
                 "ORDER BY ts DESC LIMIT 3").fetchall()
print("последние пробы:")
for р in посл:
    print(f"   {str(р['ts'])[:19]}  {str(р['email'])[:34]:<34} "
          f"{р['verdict']} ({р['source']})")
print("источники за сутки:", dict(Counter(
    str(р[0]) for р in c.execute(
        "SELECT source FROM addr_probe WHERE ts >= '2026-08-23'"))))

# загруженные 24.08 компании - сколько из них проверено
проба = {str(р["email"]).lower(): str(р["verdict"] or "")
         for р in c.execute("SELECT email, verdict FROM addr_probe") if р["email"]}
новые = [str(р[0] or "").lower() for р in c.execute(
    "SELECT email FROM recipients WHERE substr(created_at,1,10)='2026-08-24'")]
есть = sum(1 for э in новые if э in проба)
print(f"\nзагружено 24.08: {len(новые)}; из них с вердиктом: {есть}; "
      f"без проверки: {len(новые)-есть}")
print("вердикты у проверенных:", dict(Counter(
    проба[э] for э in новые if э in проба).most_common(6)))

print("\n=== 2. ГЕНЕРАЦИЯ ===")
for д, метка in (("2026-08-24", "сегодня"),):
    н = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE "
                  "substr(created_at,1,10)=?", (д,)).fetchone()[0]
    print(f"карточек писем заведено {метка}: {н}")
свежие = c.execute(
    "SELECT campaign_id, substr(created_at,12,5) когда, email, subject "
    "  FROM confirm_reviews WHERE created_at >= '2026-08-24T07:00' "
    " ORDER BY id DESC LIMIT 8").fetchall()
print(f"писем после подъёма сервера (с 07:00): "
      f"{c.execute(chr(83)+'ELECT COUNT(*) FROM confirm_reviews WHERE created_at >= ?', ('2026-08-24T07:00',)).fetchone()[0]}")
for р in свежие:
    print(f"   {р['когда']} камп{р['campaign_id']} {str(р['email'])[:30]:<30} "
          f"{str(р['subject'])[:44]}")

print("\n=== журналы прогонов ===")
for п in sorted(glob.glob(r"C:\sender\_ops\partiya_gen-0824-*.log"),
                key=os.path.getmtime)[-2:]:
    т = io.open(п, encoding="utf-8", errors="replace").read()
    возраст = int((time.time() - os.path.getmtime(п)) // 60)
    print(f"\n-- {os.path.basename(п)} ({len(т)} знаков, обновлён "
          f"{возраст} мин назад)")
    for с in т.splitlines()[-6:]:
        print("   " + с[:150])
