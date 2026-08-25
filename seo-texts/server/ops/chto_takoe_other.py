# -*- coding: utf-8 -*-
"""Что легло в ленту как «other» — служебка или потерянный ответ живого человека.

«other» это входящее, которое сторож не смог привязать: не ответ на нашу
нитку, не отчёт о недоставке, не жалоба. Обычно это отчёт DMARC или письмо
маяка. Но если так лёг настоящий ответ, лид потерян молча — потому и
смотрим текстом, а не типом. Строка на событие, чтобы влезло всё.
"""
import json
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row


def разряд(т):
    т = т.lower()
    if "dmarc" in т or "report domain" in т:
        return "отчёт DMARC"
    if ("отпуск" in т or "не на месте" in т or "автоответ" in т
            or "out of office" in т or "отсутств" in т):
        return "АВТООТВЕТ ЖИВОГО ЧЕЛОВЕКА"
    if "подтвердите" in т or "confirm" in т:
        return "подтверждение подписки"
    return "разобрать глазами"


ряды = c.execute(
    "SELECT id, event_ts, mailbox_id, recipient_id, detail_json FROM events "
    " WHERE event_type='other' ORDER BY id DESC LIMIT 60").fetchall()
разряды = Counter()
сегодня = []
for р in ряды:
    try:
        d = json.loads(р["detail_json"] or "{}")
    except Exception:  # noqa: BLE001
        d = {}
    т = str(d.get("snippet") or d.get("body") or "")
    к = разряд(т)
    разряды[к] += 1
    if str(р["event_ts"]).startswith("2026-08-25"):
        сегодня.append((р, к, т))

print("последние 60 событий «other»:")
for к, н in разряды.most_common():
    print("   %-32s %4d" % (к, н))
print("\n=== СЕГОДНЯШНИЕ (%d) ===" % len(сегодня))
for р, к, т in сегодня:
    print("   #%-7s %s %-36s %-26s %s"
          % (р["id"], str(р["event_ts"])[11:19], (р["mailbox_id"] or "-")[:36],
             к, т.replace("\n", " ")[:52]))
