# -*- coding: utf-8 -*-
"""Письма КЦ — в конец очереди автоотправки (владелец 26.10: «перекинь письма кц
в конец очереди, я там закинул много в автоотправку и могут мешать» — КЦ на
паузе, его наступившие письма занимают проход раньше Meyer).
Наступившим (scheduled_at <= сейчас) письмам КЦ в статусе scheduled ставим время
«самое позднее письмо Meyer в очереди + секунды» — проход сперва разбирает Meyer.
Журнал _ops/kc-v-konec.jsonl; --otkat возвращает прежнее время (сделать, когда
владелец снимет паузу КЦ, иначе КЦ будет ждать до этого времени).
    kc_v_konec.py [--primenit | --otkat]"""
import io
import json
import sqlite3
import sys
from datetime import datetime, timedelta

ЖУР = r"C:\sender\_ops\kc-v-konec.jsonl"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=120)
if "--otkat" in sys.argv:
    з = [json.loads(s) for s in io.open(ЖУР, encoding="utf-8")]
    with c:
        for x in reversed(з):
            c.execute("UPDATE messages SET scheduled_at=? WHERE id=? AND status='scheduled' AND scheduled_at=?",
                      (x["bylo"], x["id"], x["stalo"]))
    print("откат:", len(з))
    sys.exit()
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
мей = [k for k, v in кам.items() if "meyer" in str(v).lower() or "мейер" in str(v).lower()]
кц = [k for k in кам if k not in мей]
сейчас = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
макс_мей = c.execute("SELECT MAX(scheduled_at) FROM messages WHERE status='scheduled' AND campaign_id IN (%s)"
                     % ",".join(map(str, мей))).fetchone()[0] or сейчас
# не только наступившие: письма КЦ, которые наступят раньше последнего письма
# Meyer, тоже встанут впереди него — сдвигаем все такие
ряды = c.execute("SELECT id, scheduled_at, campaign_id FROM messages WHERE status='scheduled' AND scheduled_at<=? "
                 "AND campaign_id IN (%s) ORDER BY scheduled_at, id" % ",".join(map(str, кц)), (макс_мей,)).fetchall()
from collections import Counter  # noqa: E402
print("писем КЦ раньше последнего Meyer:", len(ряды), dict(Counter(кам[r[2]] for r in ряды)))
print("самое позднее письмо Meyer в очереди:", макс_мей)
база = max(datetime.fromisoformat(str(макс_мей)[:19]), datetime.utcnow()) + timedelta(minutes=1)
if "--primenit" not in sys.argv:
    print("СУХОЙ ПРОГОН. Применить — --primenit")
    sys.exit()
with c, io.open(ЖУР, "a", encoding="utf-8") as ж:
    for i, (mid, было, _) in enumerate(ряды):
        стало = (база + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%S.%f")
        c.execute("UPDATE messages SET scheduled_at=? WHERE id=? AND status='scheduled'", (стало, mid))
        ж.write(json.dumps({"id": mid, "bylo": было, "stalo": стало}) + "\n")
print("ПРИМЕНЕНО: письма КЦ в конце, с", база)
