# -*- coding: utf-8 -*-
"""Блок получателя в промпте письма (без вызова модели): prompt_kartochki.py <rid> [<rid>…]."""
import re
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.ai_quota import build_ai_quota  # noqa: E402
from sender import ai_letter as al  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
import sqlite3 as _sq
_c = _sq.connect(r"C:\sender\sender.db")
_рег = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--re" else None
_ид = sys.argv[1:] if not _рег else []
if sys.argv[1:2] == ["--email"]:
    _ид = [str(_c.execute("SELECT id FROM recipients WHERE lower(email)=?", (е.lower(),)).fetchone()[0])
           for е in sys.argv[2:]]
    _рег = r"Контакт|кому|ФИО|имя"
for rid in _ид:
    rec = store.get_recipient(int(rid))
    req = q._request(rec)
    print("##### %s | ex.email=%r rec.email=%r | contact_name=%r fio=%r role=%r src=%r | сегмент=%r | okved=%r | activity=%r" % (rid, (req.get("extra") or {}).get("email"), req.get("email"), req.get("contact_name"), (req.get("extra") or {}).get("fio"), (req.get("extra") or {}).get("role"), (req.get("extra") or {}).get("contact_source"), req.get("segment"),
          req.get("okved"), str(req.get("activity"))[:120]))
    блок = al._recipient_block(0, req, "meyer")
    for с in блок.splitlines():
        if re.search(_рег or r"СТАНОК|НЕПИЩЕВ|Зачем|ориентир|ЧТО ОНИ ВЫПУСКАЮТ|СЫРЬЁ|кедр|рентген", с, re.I):
            print("   " + с[:420])
print("=== ПРОМПТ ===")
