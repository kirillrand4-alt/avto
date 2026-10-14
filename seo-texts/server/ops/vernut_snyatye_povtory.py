# -*- coding: utf-8 -*-
"""Вернуть в расписание письма, которые автоотправка 14.10 сняла как «уже писали»,
если повтор разрешён правилом владельца 13.10 (владелец 14.10: «да»). Каждое
проверяем заново: ConfirmSend._povtor_razreshen по последней отправке на адрес
или компанию, компания не отвечала, адрес не в стоп-листе. Возврат —
status='scheduled', срок «сейчас» (автоотправка сама подвинет в окно получателя).
Резерв — _ops/vernut-snyatye-povtory.jsonl (fsync). ЗАПУСКАТЬ ПОСЛЕ перезапуска
службы с правкой auto_send (иначе снимет снова).

    vernut_snyatye_povtory.py [--primenit]
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter
from types import SimpleNamespace

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.confirm import ConfirmSend  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402

ПРИМ = "--primenit" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
supp = Suppression(store)
cs = ConfirmSend(cfg, store, supp)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
св, вернуть = Counter(), []
for р in c.execute("SELECT m.id, m.last_error, r.email, r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                   "WHERE m.status='skipped' AND m.last_error LIKE 'auto_send:уже писали%' "
                   "AND m.updated_at >= '2026-10-14'"):
    почта = str(р["email"] or "").strip().lower()
    инн = "".join(ч for ч in str(р["inn"] or "") if ч.isdigit())
    if supp.is_suppressed(SimpleNamespace(email=почта, domain=None, inn=инн or None)) is not None:
        св["стоп-лист"] += 1
        continue
    if cs._otvechali(инн):
        св["компания отвечала"] += 1
        continue
    посл = store.last_contact(email=почта or None, inn=инн or None)
    if посл and not cs._povtor_razreshen(почта, посл):
        св["повтор правилом НЕ разрешён"] += 1
        continue
    св["вернуть"] += 1
    вернуть.append((р["id"], р["last_error"]))
print("свод: %s" % dict(св.most_common()))
if ПРИМ and вернуть:
    with io.open(r"C:\sender\_ops\vernut-snyatye-povtory.jsonl", "a", encoding="utf-8") as ж:
        for mid, ош in вернуть:
            ж.write(json.dumps({"message_id": mid, "bylo": ош}, ensure_ascii=False) + "\n")
        ж.flush()
        os.fsync(ж.fileno())
    сейчас = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    n = 0
    for mid, _ in вернуть:
        n += c.execute("UPDATE messages SET status='scheduled', scheduled_at=?, last_error=NULL, updated_at=? "
                       "WHERE id=? AND status='skipped'", (сейчас, сейчас, mid)).rowcount
    c.commit()
    print("возвращено в расписание: %d" % n)
print("=== ВЕРНУТЬ СНЯТЫЕ ПОВТОРЫ: %s ===" % ("ПРИМЕНЕНО" if ПРИМ else "сухой прогон"))
