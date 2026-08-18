# -*- coding: utf-8 -*-
"""Жёсткая отбивка обязана осесть во ВСЕХ трёх базах, а не только в стоп-листе.

Замер 18.08 по девяти адресам с жёсткой отбивкой (сервер прямо сказал
«invalid mailbox» / «unknown user»):
  * в стоп-листе панели  - 8 из 9;
  * вердикт пробы обновлён - 1 из 9. У семи в addr_probe до сих пор стоит
    «принимает всё» или «есть»;
  * три письма ВСЁ ЕЩЁ висят approved.

То есть отбивка кладёт адрес в стоп-лист - и на этом останавливается. Проба
продолжает считать адрес живым, а по правилу из CLAUDE.md вердикт обязан
попасть в три места, у каждого своя роль:
  sender.db/addr_probe            - кэш панели, заслон подтверждения;
  enrich.db/emails.probe_verdict  - обогащение, отбор кандидатов;
  obzvon-index.db/email_probe     - база обзвона на 161к.
Иначе мёртвый адрес будет ловиться на последнем рубеже каждый раз заново.

Приговором считаем ТОЛЬКО жёсткую отбивку (verdict=hard в DSN): сервер
получателя прямо сказал, что ящика нет. Отбивку по политике
(«blocked due to security reason») приговором НЕ считаем - там адрес живой,
завернули письмо.

Без аргумента - сухой прогон.

    python zapusk_svoego_skripta.py ops/hard_otbivka_v_tri_bazy.py
    python zapusk_svoego_skripta.py ops/hard_otbivka_v_tri_bazy.py --применить
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

ENRICH = r"C:\sender\enrich.db"
OBZVON = r"C:\sender\obzvon-index.db"
ПРИМЕНИТЬ = "--применить" in sys.argv
ВЕРДИКТ = "нет ящика"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    ряд = store._conn.execute(
        "SELECT DISTINCT lower(r.email), e.detail_json FROM events e "
        "JOIN recipients r ON r.id=e.recipient_id "
        "WHERE e.event_type IN ('bounce','dsn') "
        "AND e.detail_json LIKE '%\"verdict\": \"hard\"%'").fetchall()
адреса = {}
for email, dj in ряд:
    try:
        d = (json.loads(dj or "{}").get("dsn") or {})
    except Exception:                                           # noqa: BLE001
        d = {}
    адреса[email] = str(d.get("diagnostic") or "")[:200]
print(f"адресов с жёсткой отбивкой: {len(адреса)}")
for a, диаг in адреса.items():
    print(f"  {a:<38} {диаг[:80]}")

if not ПРИМЕНИТЬ:
    print("\nсухой прогон: ничего не записано. Применить - --применить")
    raise SystemExit(0)

сейчас = datetime.now(timezone.utc).isoformat()
итог = {"addr_probe": 0, "enrich": 0, "obzvon": 0, "снято_писем": 0,
        "стоп-лист": 0}

# 1. addr_probe в sender.db
for a, диаг in адреса.items():
    try:
        with store._lock:
            store._conn.execute(
                "INSERT INTO addr_probe (email, verdict, code, answer, mx, ts) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(email) DO UPDATE SET "
                "verdict=excluded.verdict, answer=excluded.answer, ts=excluded.ts",
                (a, ВЕРДИКТ, 550, f"жёсткая отбивка: {диаг}", "", сейчас))
            store._conn.commit()
        итог["addr_probe"] += 1
    except Exception as ex:                                     # noqa: BLE001
        print(f"  addr_probe {a}: {str(ex)[:100]}")

# 2. enrich.db/emails
if os.path.exists(ENRICH):
    try:
        con = sqlite3.connect(ENRICH, timeout=20)
        for a, диаг in адреса.items():
            con.execute(
                "UPDATE emails SET probe_verdict=?, probe_ts=?, probe_answer=? "
                "WHERE lower(email)=?", (ВЕРДИКТ, сейчас, диаг[:200], a))
            итог["enrich"] += con.total_changes and 1 or 0
        con.commit()
        con.close()
    except Exception as ex:                                     # noqa: BLE001
        print(f"  enrich.db: {str(ex)[:140]}")

# 3. obzvon-index.db/email_probe
if os.path.exists(OBZVON):
    try:
        con = sqlite3.connect(OBZVON, timeout=20)
        con.execute("CREATE TABLE IF NOT EXISTS email_probe (email TEXT PRIMARY KEY,"
                    " verdict TEXT, source TEXT, answer TEXT, ts TEXT)")
        for a, диаг in адреса.items():
            con.execute(
                "INSERT INTO email_probe (email, verdict, source, answer, ts) "
                "VALUES (?,?,?,?,?) ON CONFLICT(email) DO UPDATE SET "
                "verdict=excluded.verdict, answer=excluded.answer, ts=excluded.ts",
                (a, ВЕРДИКТ, "hard-bounce", диаг[:200], сейчас))
            итог["obzvon"] += 1
        con.commit()
        con.close()
    except Exception as ex:                                     # noqa: BLE001
        print(f"  obzvon-index.db: {str(ex)[:140]}")

# 4. снять письма этих адресов из очереди и добить стоп-лист
for a, диаг in адреса.items():
    try:
        with store._lock:
            cur = store._conn.execute(
                "UPDATE confirm_reviews SET status='skipped', "
                "reason='жёсткая отбивка: ящика нет', updated_at=datetime('now') "
                "WHERE lower(email)=? AND status IN ('pending','approved')", (a,))
            итог["снято_писем"] += cur.rowcount
            store._conn.commit()
        уже = store.suppression_hit(email=a) if hasattr(
            store, "suppression_hit") else None
        if уже is None:
            with store._lock:
                store._conn.execute(
                    "INSERT OR IGNORE INTO suppression (scope, value, reason, "
                    "source, created_at) VALUES ('email',?,?,?,datetime('now'))",
                    (a, "hard_bounce", "ops:hard_otbivka_v_tri_bazy"))
                store._conn.commit()
            итог["стоп-лист"] += 1
    except Exception as ex:                                     # noqa: BLE001
        print(f"  очередь/стоп-лист {a}: {str(ex)[:110]}")

print("\nзаписано:")
for k, v in итог.items():
    print(f"  {k}: {v}")
