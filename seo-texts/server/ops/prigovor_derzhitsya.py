# -*- coding: utf-8 -*-
"""Держится ли приговор доставки: замер по трём базам плюс живая попытка стереть.

Проверяем не намерение, а факт: берём адреса с жёсткой отбивкой, смотрим, что
стоит в каждой из трёх баз, и ПРЯМО ЗДЕСЬ пробуем записать поверх «есть» тем
же вызовом, каким это делает работник проб. Запись обязана не пройти.

    python zapusk_svoego_skripta.py ops/prigovor_derzhitsya.py
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.addr_probe import AddrProbe, ЕСТЬ                    # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ENRICH = r"C:\sender\enrich.db"
OBZVON = r"C:\sender\obzvon-index.db"
ПОДОПЫТНЫЙ = "kk@vebfabrika.ru"

cfg = Config.load(r"C:\sender\sender.yaml")
БАЗА = cfg.get("service.db_path", r"C:\sender\sender.db")
store = Store(БАЗА)

with store._lock:
    ряд = store._conn.execute(
        "SELECT DISTINCT lower(r.email) FROM events e "
        "JOIN recipients r ON r.id=e.recipient_id "
        "WHERE e.event_type IN ('bounce','dsn') "
        "AND e.detail_json LIKE '%\"verdict\": \"hard\"%'").fetchall()
адреса = [a for (a,) in ряд]
print(f"адресов с жёсткой отбивкой: {len(адреса)}\n")

# 1. sender.db/addr_probe
with store._lock:
    строки = {r[0]: (r[1], r[2], r[3]) for r in store._conn.execute(
        "SELECT email, verdict, source, ts FROM addr_probe WHERE email IN (%s)"
        % ",".join("?" * len(адреса)), адреса)}
print(f"{'адрес':<30} {'addr_probe':<14} {'источник':<12} "
      f"{'enrich':<12} {'обзвон':<12} писем_в_очереди")

# 2. enrich.db
ен = {}
if os.path.exists(ENRICH):
    c = sqlite3.connect(ENRICH, timeout=20)
    for a in адреса:
        r = c.execute("SELECT probe_verdict FROM emails WHERE lower(email)=?",
                      (a,)).fetchone()
        ен[a] = (r[0] if r else "нет строки") or "пусто"
    c.close()

# 3. obzvon-index.db
об = {}
if os.path.exists(OBZVON):
    c = sqlite3.connect(OBZVON, timeout=20)
    try:
        for a in адреса:
            r = c.execute("SELECT verdict FROM email_probe WHERE email=?",
                          (a,)).fetchone()
            об[a] = r[0] if r else "нет строки"
    except sqlite3.OperationalError as ex:
        об = {a: f"нет таблицы ({str(ex)[:30]})" for a in адреса}
    c.close()

for a in адреса:
    в, ист, _ts = строки.get(a, ("НЕТ СТРОКИ", "", ""))
    with store._lock:
        n = store._conn.execute(
            "SELECT COUNT(*) FROM confirm_reviews WHERE lower(email)=? "
            "AND status IN ('pending','approved')", (a,)).fetchone()[0]
    print(f"{a:<30} {в or '-':<14} {ист or '-':<12} "
          f"{ен.get(a, '-'):<12} {об.get(a, '-'):<12} {n}")

# 4. Живая попытка стереть приговор — тем же вызовом, что у работника проб.
print(f"\nпробуем записать «{ЕСТЬ}» поверх приговора ({ПОДОПЫТНЫЙ}):")
п = AddrProbe(БАЗА)
до = (п.cached(ПОДОПЫТНЫЙ) or {}).get("verdict")
легло = п._save(ПОДОПЫТНЫЙ, ЕСТЬ, 250, "2.1.5 Ok (проверка заслона)", "mx")
после = (п.cached(ПОДОПЫТНЫЙ) or {}).get("verdict")
print(f"  было: {до} | _save вернул: {легло} | стало: {после}")
print("  ЗАСЛОН ДЕРЖИТ" if легло is False and после == до
      else "  ЗАСЛОН НЕ СРАБОТАЛ")

# 5. Что лежит в результатах работника — не перезапишет ли он их снова.
рез = r"C:\sender\_ops\probe-rezultat.jsonl"
if os.path.exists(рез):
    свои = []
    for s in open(рез, encoding="utf-8", errors="replace"):
        try:
            z = json.loads(s)
        except Exception:                                       # noqa: BLE001
            continue
        if str(z.get("email") or "").lower() in set(адреса):
            свои.append((z.get("email"), z.get("verdict")))
    print(f"\nстрок работника про эти адреса в {рез}: {len(свои)}")
    for e, v in свои[-10:]:
        print(f"  {e}: {v}")
else:
    print(f"\n{рез}: файла нет (работник кладёт результат на дроп)")
