# -*- coding: utf-8 -*-
"""Напоминание по лиду (в панели своей функции напоминаний нет). Владелец 12.11: клиент ответил «напомните о себе в январе-феврале» —
сделать напоминание на начало февраля (адрес лида передаётся аргументом, в репо его не пишем).
  --zametka "текст"   — сейчас: запись в историю лида (видна в карточке, блок «История»);
  --podnyat "текст"   — в срок (запускает запланированная задача 01.02.2027): лид снова «новый» и наверху ленты
                        (created_at = сейчас; прежняя дата — в истории), в «Потребность» дописано напоминание.
    napominanie_lid.py <email | id лида> [--zametka "..." | --podnyat "..."]"""
import json, sqlite3, sys
from datetime import datetime, timezone
em = sys.argv[1].strip().lower()
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60); c.execute("PRAGMA busy_timeout=60000"); c.row_factory = sqlite3.Row
лиды = c.execute("SELECT id, status, company_name, inn, created_at, need FROM leads WHERE %s ORDER BY id DESC" % ("id=?" if em.isdigit() else "lower(email)=?"),
                 (int(em) if em.isdigit() else em,)).fetchall()
print("лиды:", [{k: (str(x[k])[:60] if k == "need" else x[k]) for k in x.keys()} for x in лиды])
if not лиды: raise SystemExit("лид не найден")
л = лиды[0]; т = datetime.now(timezone.utc).isoformat(timespec="seconds")
арг = lambda к: sys.argv[sys.argv.index(к) + 1] if к in sys.argv else ""
if "--zametka" in sys.argv:
    c.execute("INSERT INTO lead_events (lead_id, action, detail_json, created_at) VALUES (?, 'note', ?, ?)",
              (л["id"], json.dumps({"напоминание": арг("--zametka")}, ensure_ascii=False), т)); c.commit()
    print("заметка записана в лид", л["id"])
elif "--podnyat" in sys.argv:
    текст = арг("--podnyat")
    c.execute("UPDATE leads SET status='new', created_at=?, updated_at=?, need=? , version=version+1 WHERE id=?",
              (т, т, ("НАПОМИНАНИЕ: " + текст + ((" | " + л["need"]) if л["need"] else ""))[:1000], л["id"]))
    c.execute("INSERT INTO lead_events (lead_id, action, from_status, to_status, detail_json, created_at) VALUES (?, 'note', ?, 'new', ?, ?)",
              (л["id"], л["status"], json.dumps({"напоминание": текст, "прежняя дата создания": л["created_at"]}, ensure_ascii=False), т)); c.commit()
    print("лид", л["id"], "поднят наверх ленты как новый")
