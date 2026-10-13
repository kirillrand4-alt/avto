# -*- coding: utf-8 -*-
"""Получатели групп с мёртвым адресом: есть ли следующий по лесенке.

Владелец 13.10: «у 116 адрес мёртв — и нет следующего?». Следующий — адрес
той же компании из обогащения: не мёртв по пробе, не «не для письма», на него
не уходило писем, он не заведён другим получателем; порядок — лесенка ролей
(lead_scoring._rol_ball). С --primenit меняем адрес получателя на лучший
ЖИВОЙ («есть»/«принимает всё»), журнал с fsync для отката.

    zamena_myortvyh.py [--primenit]
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter
sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
try:
    from lead_scoring import _rol_ball  # noqa: E402
except Exception:  # noqa: BLE001
    def _rol_ball(р):
        return 0
ПРИМЕНИТЬ = "--primenit" in sys.argv
ЖУРНАЛ = r"C:\sender\_ops\zamena-myortvyh.jsonl"
МЁРТВ = ("нет ящика", "нет MX")
ЖИВ = ("есть", "принимает всё")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
cx.row_factory = sqlite3.Row
вер = {р[0].lower(): р[1] for р in c.execute("SELECT email, verdict FROM addr_probe")}
заняты = {р[0].lower() for р in c.execute("SELECT email FROM recipients")}
ушло = {р[0].lower() for р in c.execute(
    "SELECT DISTINCT r.email FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sent'")}
генерировали = set()
for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8", errors="replace"):
    try:
        генерировали.add(json.loads(с).get("recipient_id"))
    except Exception:  # noqa: BLE001
        pass
мёртвые = []
for р in c.execute("SELECT id, inn, lower(email) e, segment, extra_json FROM recipients WHERE extra_json LIKE '%gruppy%'"):
    try:
        гр = (json.loads(р["extra_json"] or "{}") or {}).get("gruppy") or []
    except Exception:  # noqa: BLE001
        continue
    if any(г in гр for г in ("Россия 9000", "Белорусь 1000")) and вер.get(р["e"]) in МЁРТВ:
        мёртвые.append(dict(р))
св = Counter()
св_чужие = [0]
замены = []
ПУБЛИЧНЫЕ = {"mail.ru", "bk.ru", "list.ru", "inbox.ru", "yandex.ru", "ya.ru", "gmail.com", "rambler.ru"}
for р in мёртвые:
    кандидаты = []
    к = cx.execute("SELECT site FROM companies WHERE inn=?", (р["inn"],)).fetchone()
    сайт = str((к and к["site"]) or "").lower().replace("www.", "").split("/")[0]
    # только домен САЙТА компании: домен мёртвого адреса бывает общим
    # провайдером (orel.ru), и «соседний» ящик там — чужая организация
    свои = {сайт} if сайт and сайт not in ПУБЛИЧНЫЕ else set()
    for а in cx.execute("SELECT lower(email) e, role, probe_verdict pv FROM emails WHERE inn=?", (р["inn"],)):
        е, роль = а["e"], str(а["role"] or "")
        if not е or е == р["e"] or "не для письма" in роль.lower() or _rol_ball(роль) <= 1:
            continue
        v = вер.get(е) or а["pv"]
        if v in МЁРТВ or е in ушло or е in заняты:
            continue
        дом = е.rsplit("@", 1)[-1]
        if not свои or (дом not in свои and not any(дом.endswith("." + с) for с in свои)):
            св_чужие[0] += 1
            continue
        кандидаты.append((0 if v in ЖИВ else 1, -_rol_ball(роль), е, роль, v or "не проверен"))
    кандидаты.sort()
    if not кандидаты:
        св["следующего НЕТ"] += 1
        continue
    лучший = кандидаты[0]
    св["есть следующий: " + ("живой по пробе" if лучший[0] == 0 else "ещё не проверен/неясно")] += 1
    if лучший[0] == 0:
        замены.append((р, лучший))
print("получателей групп с мёртвым адресом: %d (ещё не генерировали: %d)" % (
    len(мёртвые), sum(1 for р in мёртвые if р["id"] not in генерировали)))
for к, n in св.most_common():
    print("   %-44s %d" % (к, n))
print("   (адресов с чужим доменом пропущено: %d)" % св_чужие[0])
for р, л in замены[:8]:
    print("   %s: %s → %s (%s, %s)" % (р["id"], р["e"], л[2], л[3][:20], л[4]))
if ПРИМЕНИТЬ and замены:
    with io.open(ЖУРНАЛ, "a", encoding="utf-8") as ж, c:
        for р, л in замены:
            c.execute("UPDATE recipients SET email=?, domain=? WHERE id=?", (л[2], л[2].split("@")[-1], р["id"]))
            ж.write(json.dumps({"ts": int(time.time()), "rid": р["id"], "было": р["e"], "стало": л[2],
                                "роль": л[3], "проба": л[4]}, ensure_ascii=False) + "\n")
        ж.flush()
        os.fsync(ж.fileno())
    print("=== ЗАМЕНА МЁРТВЫХ: ПРИМЕНЕНО (%d) ===" % len(замены))
else:
    print("=== ЗАМЕНА МЁРТВЫХ: СУХОЙ ПРОГОН ===")
