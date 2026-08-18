# -*- coding: utf-8 -*-
"""Ответы, где нам дали ДРУГОЙ адрес: «пишите вот сюда» и автоответы отпуска.

Такой ответ - это не отказ, а переадресация, и она дороже обычного лида:
человек назвал коллегу поимённо. Достаём адрес из текста, отсеиваем свои
домены и адрес самого отправителя.
"""
import json
import re
import sys
from collections import OrderedDict

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.pismo_v_tekst import v_tekst                         # noqa: E402
from sender.store import Store                                   # noqa: E402

АДРЕС = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
наши = {m.mailbox_id.split("@")[-1].lower() for m in cfg.mailboxes()}

with store._lock:
    ряд = store._conn.execute(
        """SELECT e.id, e.event_ts, e.recipient_id, e.detail_json,
                  r.email, r.company_name, r.inn
             FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id
            WHERE e.event_type IN ('reply','reply_auto')
            ORDER BY e.event_ts DESC LIMIT 200""").fetchall()

найдено = OrderedDict()
for eid, ts, rid, dj, email, фирма, inn in ряд:
    try:
        d = json.loads(dj or "{}")
    except Exception:                                            # noqa: BLE001
        d = {}
    текст = v_tekst(str(d.get("snippet") or ""))
    # Цитату нашего письма отрезаем: в ней наш адрес и адрес получателя.
    цитата = текст.find("----------------")
    ядро = текст[:цитата] if цитата > 0 else текст[:1200]
    чужие = []
    for a in АДРЕС.findall(ядро):
        д = a.split("@")[-1].lower()
        if д in наши:
            continue
        if email and a.lower() == str(email).lower():
            continue
        if a.lower() not in [x.lower() for x in чужие]:
            чужие.append(a)
    if not чужие:
        continue
    найдено[eid] = {
        "когда": str(ts)[:19], "кому_писали": email, "фирма": фирма,
        "инн": inn, "recipient_id": rid, "новые_адреса": чужие,
        "ответ": ядро.strip()[:700]}

print(f"ответов с чужим адресом: {len(найдено)}\n")
for eid, z in найдено.items():
    print("=" * 72)
    print(f"событие {eid}  {z['когда']}  {z['фирма']}  ИНН {z['инн']}")
    print(f"  писали на: {z['кому_писали']}")
    print(f"  дали адрес: {', '.join(z['новые_адреса'])}")
    print(f"  ответ: {z['ответ'][:500]}")
