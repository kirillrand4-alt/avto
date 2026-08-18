# -*- coding: utf-8 -*-
"""Почему сегодня отбивок 1%, а 07-11.08 было 5% — по составу адресов.

Отбивку даёт НЕ письмо, а адрес: сервер получателя отвечает «нет такого
ящика». Значит и объяснять надо составом адресов, а не качеством текста.
Смотрим по дням: сколько отправленного ушло на адреса, которые проба
ПОДТВЕРДИЛА («есть»), сколько - на домены-catch-all («принимает всё», где
подтвердить нельзя в принципе), и сколько - вообще без пробы.

    python zapusk_svoego_skripta.py ops/kak_dobilis_odnogo_procenta.py
"""
import json
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    отправки = store._conn.execute(
        """SELECT substr(e.event_ts,1,10) d, lower(r.email),
                  COALESCE(p.verdict,'(не проверялся)')
             FROM events e
             JOIN recipients r ON r.id=e.recipient_id
             LEFT JOIN addr_probe p ON p.email=lower(r.email)
            WHERE e.event_type='sent'""").fetchall()
    отбивки = store._conn.execute(
        """SELECT substr(e.event_ts,1,10) d, e.detail_json
             FROM events e WHERE e.event_type='bounce'""").fetchall()

по_дням = defaultdict(Counter)
всего = Counter()
for d, email, вердикт in отправки:
    по_дням[d][вердикт] += 1
    всего[d] += 1

мёртвых = Counter()
for d, dj in отбивки:
    try:
        в = str((json.loads(dj or "{}").get("dsn") or {}).get("verdict") or "")
    except Exception:                                            # noqa: BLE001
        в = ""
    if в != "policy":
        мёртвых[d] += 1

print(f"{'день':<12} {'ушло':>6} {'мёртвых':>8} {'доля':>7} | "
      f"{'подтв.':>7} {'catch-all':>10} {'без пробы':>10} {'мёртв.адрес':>12}")
for d in sorted(всего):
    n = всего[d]
    c = по_дням[d]
    есть = c.get("есть", 0)
    все_подряд = c.get("принимает всё", 0)
    нет = c.get("(не проверялся)", 0) + c.get("неясно", 0) + \
        c.get("отказ пробе", 0)
    мёртв = c.get("нет ящика", 0) + c.get("нет MX", 0)
    доля = 100.0 * мёртвых.get(d, 0) / n if n else 0
    print(f"{d:<12} {n:>6} {мёртвых.get(d, 0):>8} {доля:>6.1f}% | "
          f"{100.0 * есть / n:>6.0f}% {100.0 * все_подряд / n:>9.0f}% "
          f"{100.0 * нет / n:>9.0f}% {100.0 * мёртв / n:>11.0f}%")

print("\nстолбцы: доля писем этого дня, ушедших на адрес, который проба")
print("  подтв.     — подтвердила («есть»)")
print("  catch-all  — домен принимает любой адрес, подтвердить нельзя")
print("  без пробы  — не проверяла вовсе / «неясно» / «отказ пробе»")
print("  мёртв.адрес— уже знала, что ящика нет (вердикт мог прийти ПОСЛЕ")
print("               отправки — тогда это и есть та самая отбивка)")
