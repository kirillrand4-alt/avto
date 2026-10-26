# -*- coding: utf-8 -*-
"""Ёмкость оставшихся каналов (владелец 26.10). Только чтение.
1) напоминания Meyer: последнее письмо Meyer > 15 дн., писем любого направления
   за 15 дн. не было, ответа/автоответа/жалобы/отбивки/лида нет, пилот не трогал;
2) второе касание Meyer: компании, которым Meyer писал >= 3 дн. назад, без
   ответа и т.п., у которых есть ДРУГОЙ адрес, на который ещё не писали;
3/4) Meyer / КЦ: компании базы обзвона с направлением, которым в этом
   направлении письма не было, гейт не сказал «не покупатель», есть живой адрес.
Адрес живой: проба «есть»/«принимает всё»; «без проверки» — вердикта нет;
мёртвые («нет ящика»/«нет MX») и «неясно» не считаем."""
import io
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import requests

sys.path.insert(0, r"C:\sender")
from sender.company_card import ObzvonIndex  # noqa: E402

ВЫХ = []


def п(*a):
    ВЫХ.append(" ".join(str(x) for x in a))
    print(*a, flush=True)


сейчас = datetime.utcnow()
s = sqlite3.connect(r"C:\sender\sender.db", timeout=120)
кам = {r[0]: r[1] for r in s.execute("SELECT id, name FROM campaigns")}
мей_к = {k for k, v in кам.items() if "meyer" in str(v).lower() or "мейер" in str(v).lower()}
пол = {r[0]: (str(r[1] or ""), (r[2] or "").lower()) for r in s.execute("SELECT id, inn, email FROM recipients")}
в_панели = {v[0] for v in пол.values() if v[0]}
отпр = defaultdict(list)          # инн -> [(sent_at, напр, email)]
писали_адр = set()
for rid, cid, sent in s.execute("SELECT recipient_id, campaign_id, sent_at FROM messages WHERE status='sent' AND sent_at IS NOT NULL"):
    инн, em = пол.get(rid, ("", ""))
    писали_адр.add(em)
    if инн:
        отпр[инн].append((sent, "meyer" if cid in мей_к else "kc", em, cid))
плохие = set()
for (rid,) in s.execute("SELECT DISTINCT recipient_id FROM events WHERE event_type IN ('reply','reply_auto','complaint','dsn','bounce')"):
    if rid in пол and пол[rid][0]:
        плохие.add(пол[rid][0])
for (инн,) in s.execute("SELECT DISTINCT inn FROM leads WHERE inn IS NOT NULL"):
    плохие.add(str(инн))
стоп = {(a, b.lower()) for a, b in s.execute("SELECT scope, value FROM suppression")}
проба = {r[0].lower(): r[1] for r in s.execute("SELECT email, verdict FROM addr_probe")}
не_пок = {str(r[0]) for r in s.execute("SELECT inn FROM target_verdicts WHERE verdict='не покупатель'")}
пилот = set()
try:
    пилот = {json.loads(x)["inn"] for x in io.open(r"C:\sender\_ops\napominaniya-pilot.jsonl", encoding="utf-8")}
except OSError:
    pass
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=120)
ecols = [r[1] for r in e.execute("PRAGMA table_info(emails)")]
адреса = defaultdict(set)
for r in e.execute("SELECT inn, lower(email)%s FROM emails" % (", probe_verdict" if "probe_verdict" in ecols else "")):
    if r[1]:
        адреса[str(r[0])].add(r[1])
        if len(r) > 2 and r[2] and r[1] not in проба:
            проба[r[1]] = r[2]
o = sqlite3.connect(r"file:C:\sender\obzvon-index.db?mode=ro", uri=True, timeout=120)
try:
    for em, v in o.execute("SELECT lower(email), verdict FROM email_probe"):
        проба.setdefault(em, v)
except sqlite3.Error:
    pass
ПЛОХ_ЛОК = re.compile(r"^(hr|kadr|buh|rezume|resume|job|vakans|noreply|no-reply)")


def статус(em):
    if not em or "@" not in em or ПЛОХ_ЛОК.match(em.split("@")[0]):
        return "нет"
    if ("email", em) in стоп or ("domain", em.split("@")[-1]) in стоп:
        return "нет"
    в = проба.get(em, "")
    if в in ("нет ящика", "нет MX") or в == "неясно" or (в and в not in ("есть", "принимает всё")):
        return "нет"
    return "живой" if в else "без проверки"


def лучший(адр):
    сс = [статус(a) for a in адр]
    return "живой" if "живой" in сс else ("без проверки" if "без проверки" in сс else "нет")


# 1) напоминания
р1 = Counter()
for инн, сп in отпр.items():
    мей = [x for x in сп if x[1] == "meyer"]
    if not мей or инн in плохие or инн in пилот:
        continue
    посл = max(x[0] for x in мей)
    if max(x[0] for x in сп) >= (сейчас - timedelta(days=15)).isoformat():
        continue
    ст = лучший({x[2] for x in мей})
    if ст == "нет":
        continue
    д = (сейчас - datetime.fromisoformat(посл[:19])).days
    р1[("15-30 дн." if д <= 30 else ">30 дн.", ст)] += 1
п("1) НАПОМИНАНИЯ Meyer (без пилота):", sum(р1.values()), dict(р1))

# 2) второе касание Meyer
р2 = Counter()
р2к = Counter()
for инн, сп in отпр.items():
    мей = [x for x in сп if x[1] == "meyer"]
    if not мей or инн in плохие:
        continue
    if max(x[0] for x in сп) >= (сейчас - timedelta(days=3)).isoformat():
        continue
    другие = {a for a in адреса.get(инн, ()) if a not in писали_адр}
    if not другие:
        continue
    ст = лучший(другие)
    if ст != "нет":
        р2[ст] += 1
        # по кампаниям, где компании писали Meyer (одна компания — во всех своих)
        for к in sorted({кам.get(x[3]) for x in мей}):
            р2к[к] += 1
п("2) ВТОРОЕ КАСАНИЕ Meyer (компаний с неиспользованным адресом):", sum(р2.values()), dict(р2))
п("   по кампаниям Meyer, где компании писали:", р2к.most_common())

# 3/4) не писали в направлении
ix = ObzvonIndex(r"C:\sender\obzvon-index.db")
ocols = [r[1] for r in o.execute("PRAGMA table_info(obzvon)")]
р3 = {"meyer": Counter(), "kc": Counter()}
for r in o.execute("SELECT inn, %s FROM obzvon" % ", ".join(c for c in ("emails_base", "emails_site") if c in ocols)):
    инн = str(r[0] or "")
    if not инн or инн in плохие or инн in не_пок:
        continue
    нап = ix.divisions(инн) or set()
    if not нап:
        continue
    адр = set(адреса.get(инн, set()))
    for поле in r[1:]:
        адр |= {a.lower() for a in re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", str(поле or ""))}
    ст = лучший(адр)
    if ст == "нет":
        continue
    было = {x[1] for x in отпр.get(инн, [])}
    for д in ("meyer", "kc"):
        if д in нап and д not in было:
            р3[д][("в панели" if инн in в_панели else "только в базе", ст)] += 1
п("3) MEYER — не писали, но можно:", sum(р3["meyer"].values()), dict(р3["meyer"]))
п("4) КЦ — не писали, но можно:", sum(р3["kc"].values()), dict(р3["kc"]))
т = "\n".join(ВЫХ) + "\n"
requests.put(os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/") + "/emkost-kanalov.txt",
             data=т.encode("utf-8"), headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=60)
