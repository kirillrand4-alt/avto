# -*- coding: utf-8 -*-
"""Перечитать письмо «СМК Альтернатива» из ящика и переписать карточку.

Текст в карточке разобран СТАРЫМ разборщиком — таблица рассыпалась по
словам. Письмо ещё лежит в ящике, берём его заново и раскладываем таблицу
строками.

    python perechitat_alternativu.py            # показать
    python perechitat_alternativu.py primenit   # переписать карточку и событие
"""
import json
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402
from sender.mailbrowser import MailBrowser    # noqa: E402
from sender.pismo_v_tekst import v_tekst      # noqa: E402

ДЕЛАТЬ = "primenit" in sys.argv[1:]
ЯЩИК = "l.abubakirov@compressor-store.ru"
ОТПР = "chernov@smk-alternativa.com"
СОБЫТИЕ = 218976
ЛИД = 192
БАЗА = r"C:\sender\sender.db"

cfg = Config.load(r"C:\sender\sender.yaml")
mb = MailBrowser(cfg)
д = mb.messages(ЯЩИК, folder="INBOX", limit=60)
цель = next((п for п in (д.get("messages") or [])
             if str(п.get("from_addr") or "").lower() == ОТПР), None)
if цель is None:
    print("письма в ящике не нашлось")
    raise SystemExit(1)
полное = mb.message(ЯЩИК, folder="INBOX", uid=цель["uid"])
тело = str(полное.get("body") or полное.get("text") or "")
print("=== как читается теперь ===")
print(тело[:1800])

if not ДЕЛАТЬ:
    print("\nвхолостую. Переписать карточку — primenit")
    raise SystemExit(0)

c = sqlite3.connect(БАЗА, timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row
сейчас = time.strftime("%Y-%m-%dT%H:%M:%S")
e = c.execute("SELECT detail_json FROM events WHERE id=?", (СОБЫТИЕ,)).fetchone()
if e:
    d = json.loads(e["detail_json"] or "{}")
    d["snippet"] = тело[:4000]
    d["perechitano"] = "26.08, разбор таблиц"
    c.execute("UPDATE events SET detail_json=? WHERE id=?",
              (json.dumps(d, ensure_ascii=False), СОБЫТИЕ))
    print("событие #%s переписано" % СОБЫТИЕ)
c.execute("UPDATE leads SET need=?, updated_at=? WHERE id=?",
          ("[hot, тел +7 911 655-04-57] " + тело[:5500], сейчас, ЛИД))
print("карточка лида #%s переписана" % ЛИД)
c.commit()
c.close()
