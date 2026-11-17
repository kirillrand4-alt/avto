# -*- coding: utf-8 -*-
"""Владелец 17.11: фотосепаратор на орехах видит прежде всего брак — повреждённые, потемневшие, заплесневелые.
Правка карточки «Куликовский» (cid:57585) в кампании «Meyer провалы 17.11» + запись в журнал партии.
    meyer_kulikovskiy_1711.py [--primenit]"""
import io, json, os, sqlite3, sys, time
СТ = "Речь шла о производительности около 1 т/час на один лоток для удаления пластика и скорлупы."
НВ = ("Речь шла о производительности около 1 т/час на один лоток: убрать скорлупу и пластик, "
      "а также повреждённые, потемневшие и заплесневелые орехи.")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60); c.execute("PRAGMA busy_timeout=60000")
р = c.execute("SELECT cr.id, cr.body, cr.edited_body, cr.status FROM confirm_reviews cr JOIN campaigns k ON k.id=cr.campaign_id "
              "WHERE k.name='Meyer провалы 17.11' AND lower(cr.email)='a.beksultan@kulikov.com'").fetchone()
print("карточка", р and (р[0], р[3]), "| кусок найден:", bool(р and СТ in р[1]))
if р and СТ in р[1]: print(р[1].replace(СТ, НВ))
if "--primenit" in sys.argv and р and СТ in р[1] and р[3] == "pending":
    т = time.strftime("%Y-%m-%dT%H:%M:%S")
    with c:
        c.execute("UPDATE confirm_reviews SET body=?, edited_body=?, updated_at=? WHERE id=?",
                  (р[1].replace(СТ, НВ), (р[2].replace(СТ, НВ) if р[2] else р[2]), т, р[0]))
    ж = r"C:\sender\_ops\meyer-partiya.jsonl"; з = None
    for с in io.open(ж, encoding="utf-8"):
        if с.strip() and json.loads(с)["kluch"] == "cid:57585": з = json.loads(с)
    з.update(pismo=з["pismo"].replace(СТ, НВ), ts=т)
    with io.open(ж, "a", encoding="utf-8") as ф:
        ф.write(json.dumps(з, ensure_ascii=False) + "\n"); ф.flush(); os.fsync(ф.fileno())
    print("ПРИМЕНЕНО")
