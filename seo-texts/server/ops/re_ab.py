# -*- coding: utf-8 -*-
"""Владелец 03.11: половина напоминаний с «Re:», половина без — сравнить ответы.
Делим pending-напоминания по md5(id карточки+"re") — независимо от деления шаблон/заходы
(то шло по ИНН). Метка в panel_json: re_ab = "re" | "bez_re". [--primenit]"""
import hashlib, json, re, sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
р = c.execute("SELECT id, subject, panel_json FROM confirm_reviews WHERE kind='reply' AND status='pending' "
              "AND panel_json LIKE '%napominanie%'").fetchall()
сч = {"re": 0, "bez_re": 0}
обн = []
for i, s, п in р:
    гр = "re" if int(hashlib.md5(("%dre" % i).encode()).hexdigest(), 16) % 2 == 0 else "bez_re"
    сч[гр] += 1
    чист = re.sub(r"^(?:re:\s*)+", "", s or "", flags=re.I)
    п = json.loads(п or "{}"); п["re_ab"] = гр
    обн.append(("Re: " + чист if гр == "re" else чист, json.dumps(п, ensure_ascii=False), i))
print("pending напоминаний:", len(р), сч)
if "--primenit" in sys.argv:
    with c:
        c.executemany("UPDATE confirm_reviews SET subject=?, panel_json=? WHERE id=? AND status='pending'", обн)
    print("применено")
