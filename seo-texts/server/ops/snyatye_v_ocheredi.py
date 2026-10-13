# -*- coding: utf-8 -*-
"""Адреса, снятые в книге MEYER-7 13:58 (чужой сайт, тёзки клиента со сделкой):
где они у нас — очередь/расписание/отправлено/пул генерации. Только чтение.

    snyatye_v_ocheredi.py
"""
import io
import json
import sqlite3
import sys
import time
from collections import Counter
ПРИМ = "--primenit" in sys.argv
из_групп = []
сн = json.load(io.open(r"C:\sender\server\ops\m7_snyatye_1358.json", encoding="utf-8"))["snyatye"]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
св = Counter()
ждут = []
for e in сн:
    рр = c.execute("SELECT id, company_name, inn, extra_json FROM recipients WHERE lower(email)=?", (e,)).fetchall()
    if not рр:
        св["нет у нас"] += 1
        continue
    св["есть получатель"] += 1
    for р in рр:
        if "Россия 9000" in str(р["extra_json"]) or "Белорусь 1000" in str(р["extra_json"]):
            св["в группах генерации"] += 1
            из_групп.append((р["id"], р["extra_json"]))
        for м in c.execute("SELECT id, status, campaign_id, sent_at, scheduled_at FROM messages WHERE recipient_id=?", (р["id"],)):
            св["письмо: " + м["status"]] += 1
            if м["status"] in ("pending_review", "approved", "scheduled", "sending"):
                ждут.append((м["id"], м["status"], e, р["company_name"], р["inn"]))
print("снятых адресов: %d; %s" % (len(сн), dict(св.most_common())))
for x in ждут:
    print("  ЖДЁТ ОТПРАВКИ: письмо #%s %s → %s | %s %s" % x)
if ПРИМ:
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    n = 0
    for mid, *_ in ждут:
        n += c.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=? AND status IN "
                       "('pending_review','approved','scheduled')",
                       ("книга MEYER-7 13.10: контакт снят (сайт другой организации / тёзка клиента со сделкой)", ts, mid)).rowcount
    г = 0
    with io.open(r"C:\sender\_ops\snyatye-iz-grupp-1013.jsonl", "a", encoding="utf-8") as ж:
        for rid, ex in из_групп:
            try:
                д = json.loads(ex or "{}")
            except Exception:  # noqa: BLE001
                continue
            гр = д.get("gruppy")
            if isinstance(гр, list):
                д["gruppy"] = [x for x in гр if x not in ("Россия 9000", "Белорусь 1000")]
            elif isinstance(гр, str):
                д["gruppy"] = ";".join(x for x in гр.split(";") if x.strip() not in ("Россия 9000", "Белорусь 1000"))
            д["snyat_knigoy"] = "MEYER-7 13.10 13:58: контакт снят"
            ж.write(json.dumps({"rid": rid, "bylo": ex}, ensure_ascii=False) + "\n")
            г += c.execute("UPDATE recipients SET extra_json=? WHERE id=?", (json.dumps(д, ensure_ascii=False), rid)).rowcount
        ж.flush()
        import os
        os.fsync(ж.fileno())
    c.commit()
    print("снято из очереди писем: %d; убрано из групп генерации: %d" % (n, г))
print("=== СНЯТЫЕ В ОЧЕРЕДИ ===")
