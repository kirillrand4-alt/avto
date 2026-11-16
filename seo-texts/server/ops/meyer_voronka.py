# -*- coding: utf-8 -*-
"""Воронка партии «провалы Meyer» после разметки: из размеченных к письму — сколько отсеяно стопом, письмом на тот же адрес
за 60 дней, активной сделкой КЦ, отсутствием живого адреса (проба); итог к сборке и что в журнале. Только чтение."""
import io, json
from collections import Counter
О = r"C:\sender\_ops"
кл = {json.loads(с)["kluch"]: json.loads(с) for с in io.open(О + r"\meyer-provaly-klass.jsonl", encoding="utf-8")}
комп = {json.loads(с)["kluch"]: json.loads(с) for с in io.open(О + r"\meyer-provaly2.jsonl", encoding="utf-8")}
проба = {}
for с in io.open(О + r"\proba-meyer-provaly.jsonl", encoding="utf-8"):
    x = json.loads(с); проба[x["email"].strip().lower()] = x["itog"]
сч = Counter(); пр = Counter()
for к, р in кл.items():
    ш = р.get("shablon"); x = комп.get(к)
    if ш == "NE_PISAT": сч["1 разметка: не писать"] += 1; continue
    if not x: сч["нет в выборке"] += 1; continue
    if x.get("stop"): сч["2 стоп-лист"] += 1; continue
    if x.get("pisali60"): сч["3 на этот адрес писали за 60 дней"] += 1; continue
    if x.get("aktiv_kc"): сч["4 активная сделка КЦ"] += 1; continue
    в = [проба.get(e.strip().lower(), "не проверен") for e in x["emails"]]
    if "есть" in в or "принимает всё" in в: сч["5 К СБОРКЕ"] += 1; continue
    if в and all(v in ("нет ящика", "нет MX") for v in в): сч["5 все адреса мёртвые"] += 1
    else: сч["5 только неясные/не проверены"] += 1; пр.update(в)
print("размечено:", len(кл))
for к, n in sorted(сч.items()): print("  %-40s %5d" % (к, n))
print("неясные по вердиктам:", dict(пр))
ж = [json.loads(с) for с in io.open(О + r"\meyer-partiya.jsonl", encoding="utf-8")]
print("журнал сборки:", len(ж), dict(Counter(з["status"] for з in ж)))

# 16.11: правило «мешает только письмо Meyer на тот же адрес за 15 дней» — что с бывшими «писали за 60 дней»
import sqlite3, sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config
мей = {m.mailbox_id for m in Config.load(r"C:\sender\sender.yaml").mailboxes() if str(getattr(m, "division", "")) == "meyer"}
порог = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()[:19]
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
недавно = {e for e, mb in c.execute("SELECT lower(r.email), m.mailbox_id FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sent' AND m.sent_at>=?", (порог,)) if mb in мей}
б = Counter()
for к, р in кл.items():
    x = комп.get(к)
    if р.get("shablon") == "NE_PISAT" or not x or x.get("stop") or not x.get("pisali60") or x.get("aktiv_kc"): continue
    живые = [e.strip().lower() for e in x["emails"] if проба.get(e.strip().lower()) in ("есть", "принимает всё")]
    if not живые: б["нет живого адреса"] += 1
    elif all(e in недавно for e in живые): б["Meyer писал на адрес за 15 дней"] += 1
    else: б["вернулась"] += 1
print("бывшие «писали за 60 дней»:", dict(б))
