# -*- coding: utf-8 -*-
"""Лиды, закрытые как «не интересно», к которым ПОТОМ пришёл ответ.

Время закрытия берём из журнала переходов lead_events, а не из updated_at:
updated_at двигает любой новый ответ, и по нему закрытие неотличимо от
обновления. Ответы ищем по ВСЕЙ компании (по ИНН), а не по одному
получателю: у ИМСБ первый ответ пришёл с kunizin@gmail.com, а второй — с
rouk@imsb.ru на письмо, посланное на secretar@imsb.ru.
"""
import json
import sqlite3
from collections import Counter

БАЗА = r"C:\sender\sender.db"
СКРЫТЫЕ = ("deleted", "not_interested", "in_bitrix", "unqualified")

c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=120)
c.row_factory = sqlite3.Row

print("=== СХЕМА lead_events ===")
поля = [r[1] for r in c.execute("PRAGMA table_info(lead_events)")]
print("   " + ", ".join(поля))
пример = c.execute("SELECT * FROM lead_events ORDER BY id DESC LIMIT 2").fetchall()
for r in пример:
    print("   " + json.dumps({к: str(r[к])[:70] for к in r.keys()
                              if r[к] not in (None, "")}, ensure_ascii=False))

# ИНН -> получатели компании
по_инн = {}
for r in c.execute("SELECT id, inn FROM recipients WHERE COALESCE(inn,'')<>''"):
    по_инн.setdefault(str(r["inn"]), set()).add(int(r["id"]))

# ответы: получатель -> список времён
ответы = {}
for r in c.execute(
        "SELECT id, recipient_id, event_ts FROM events WHERE event_type='reply'"):
    ответы.setdefault(int(r["recipient_id"] or 0), []).append(
        (str(r["event_ts"] or ""), int(r["id"])))

лиды = [dict(r) for r in c.execute("SELECT * FROM leads")]

# когда лид стал скрытым — по журналу переходов
когда_закрыт = {}
кто_закрыл = {}
поле_ст = next((п for п in поля if п in ("to_status", "status", "new_status")),
               None)
поле_вр = next((п for п in поля if п in ("created_at", "ts", "event_ts")), None)
поле_кто = next((п for п in поля if "actor" in п or п == "decided_by"), None)
if поле_ст and поле_вр:
    зпр = ("SELECT lead_id, %s AS ст, %s AS вр%s FROM lead_events ORDER BY id"
           % (поле_ст, поле_вр, (", %s AS кто" % поле_кто) if поле_кто else ""))
    for r in c.execute(зпр):
        if str(r["ст"] or "") in СКРЫТЫЕ:
            когда_закрыт[int(r["lead_id"])] = str(r["вр"] or "")
            if поле_кто:
                кто_закрыл[int(r["lead_id"])] = str(r["кто"] or "")
c.close()

находки = []
счёт = Counter()
for л in лиды:
    if str(л.get("status") or "") not in СКРЫТЫЕ:
        continue
    счёт["скрытых лидов"] += 1
    закрыт = когда_закрыт.get(int(л["id"])) or str(л.get("created_at") or "")
    if not закрыт:
        счёт["без времени закрытия"] += 1
        continue
    свои = по_инн.get(str(л.get("inn") or ""), set())
    свои.add(int(л.get("recipient_id") or 0))
    позже = []
    for rid in свои:
        for вр, eid in ответы.get(rid, []):
            if вр > закрыт:
                позже.append((вр, eid, rid))
    if позже:
        позже.sort()
        находки.append((л, закрыт, позже))
        счёт["ОТВЕТ ПОСЛЕ ЗАКРЫТИЯ"] += 1

находки.sort(key=lambda x: x[2][-1][0], reverse=True)

print("")
print("=" * 78)
print("=== СВОДКА: ОТВЕТЫ ПОСЛЕ ЗАКРЫТИЯ ЛИДА ===")
for к, в in счёт.most_common():
    print("   %-26s %5d" % (к, в))
print("")
for л, закрыт, позже in находки[:25]:
    print("--- лид %s | %s | ИНН %s | статус %s"
          % (л["id"], str(л.get("company_name") or "")[:40], л.get("inn"),
             л.get("status")))
    print("    закрыт %s%s" % (закрыт[:19],
                               ("  кем: " + кто_закрыл.get(int(л["id"]), ""))
                               if кто_закрыл.get(int(л["id"])) else ""))
    for вр, eid, rid in позже[-3:]:
        print("    ОТВЕТ %s  событие %s  получатель %s" % (вр[:19], eid, rid))
    print("    текст: %s" % str(л.get("need") or "").replace("\n", " ")[:150])
