# -*- coding: utf-8 -*-
"""Снять приговор доставки с адреса — обратный ход к hard_otbivka_v_tri_bazy.

Приговор нарочно несбиваемый: проба его не перебивает, TTL его не протухает.
Значит и снимать его должен человек осознанно — например, если контора
завела ящик заново и написала нам с него сама.

Снимает во всех трёх базах и вынимает адрес из стоп-листа. Без --снять
только показывает, что стоит сейчас.

    python zapusk_svoego_skripta.py ops/snyat_prigovor_s_adresa.py kk@vebfabrika.ru
    python zapusk_svoego_skripta.py ops/snyat_prigovor_s_adresa.py kk@vebfabrika.ru --снять
"""
import os
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ENRICH = r"C:\sender\enrich.db"
OBZVON = r"C:\sender\obzvon-index.db"
СНЯТЬ = "--снять" in sys.argv
адреса = [a.strip().lower() for a in sys.argv[1:]
          if a and not a.startswith("--")]
if not адреса:
    print("укажи адрес(а)")
    raise SystemExit(2)

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

for a in адреса:
    with store._lock:
        p = store._conn.execute(
            "SELECT verdict, source, ts FROM addr_probe WHERE email=?",
            (a,)).fetchone()
        s = store._conn.execute(
            "SELECT reason, source FROM suppression WHERE scope='email' "
            "AND lower(value)=?", (a,)).fetchall()
    print(f"{a}: addr_probe={tuple(p) if p else 'нет строки'} "
          f"стоп-лист={[tuple(x) for x in s]}")

if not СНЯТЬ:
    print("\nсухой прогон: ничего не изменено. Снять — аргумент --снять")
    raise SystemExit(0)

for a in адреса:
    with store._lock:
        store._conn.execute("DELETE FROM addr_probe WHERE email=?", (a,))
        store._conn.execute("DELETE FROM suppression WHERE scope='email' "
                            "AND lower(value)=? AND reason IN "
                            "('bounce_hard','hard_bounce')", (a,))
        store._conn.commit()
    if os.path.exists(ENRICH):
        c = sqlite3.connect(ENRICH, timeout=20)
        c.execute("UPDATE emails SET probe_verdict=NULL, probe_ts=NULL, "
                  "probe_answer=NULL WHERE lower(email)=?", (a,))
        c.commit()
        c.close()
    if os.path.exists(OBZVON):
        c = sqlite3.connect(OBZVON, timeout=20)
        try:
            c.execute("DELETE FROM email_probe WHERE email=?", (a,))
            c.commit()
        except sqlite3.OperationalError:
            pass
        c.close()
    print(f"снят приговор: {a}")
