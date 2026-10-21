# -*- coding: utf-8 -*-
"""Кого из «ФСА волна 1» не пустили в генерацию Meyer и насколько это верно
(владелец 21.10). По каждому адресу группы: стоп-лист (с причиной), заслон
повтора (какое письмо и когда), направление, «не наш»/«не покупатель» (с
доводом), уже есть письмо Meyer. Только чтение."""
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.confirm import ConfirmSend      # noqa: E402
from sender.store import Store              # noqa: E402
from sender.suppression import Suppression  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, st, Suppression(st))
c = sqlite3.connect(r"C:\sender\sender.db")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
таб = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
for rid, em, inn, имя, seg, ex in c.execute("SELECT id, lower(email), inn, company_name, segment, extra_json FROM recipients "
                                           "WHERE extra_json LIKE '%ФСА волна 1%'").fetchall():
    x = json.loads(ex or "{}")
    if "ФСА волна 1" not in (x.get("gruppy") or []):
        continue
    почему = cs._guard(inn=inn, email=em)
    подр = ""
    if почему and почему.startswith("recent_contact"):
        л = st.last_contact(email=em) or {}
        подр = "%s, %s" % (str(л.get("ts"))[:10], кам.get(л.get("campaign_id")))
        почему = "повтор"
    elif почему and почему.startswith("suppressed"):
        р = c.execute("SELECT scope, reason, source FROM suppression WHERE lower(value) IN (?,?,?)",
                      (em, em.split("@")[-1], str(inn))).fetchall()
        подр = str(р)[:120]
        почему = "стоп-лист"
    elif почему:
        почему = почему[:40]
    else:
        тв = c.execute("SELECT verdict, pochemu FROM target_verdicts WHERE inn=? ORDER BY rowid DESC LIMIT 1", (str(inn),)).fetchone() \
            if "target_verdicts" in таб else None
        if тв and тв[0] != "покупатель":
            почему, подр = "гейт: " + str(тв[0]), str(тв[1])[:120]
        elif str(seg) not in ("meyer", "") and x.get("target_division") == "kc":
            почему, подр = "направление КЦ", "сегмент " + str(seg)
    if почему:
        print("%-10s| %-34s| %-28s| %s" % (почему[:10], em[:34], str(имя).replace("ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ", "ООО")[:28], подр))
