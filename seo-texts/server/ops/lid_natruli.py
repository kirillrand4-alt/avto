# -*- coding: utf-8 -*-
"""ООО «Натрули» (ИНН 5009117027) ответило на письмо Meyer 49947 с личного giga004@mail.ru новым письмом (событие 446320).
Событие уже привязано (sobytie_446320_v_reply.py), но лид-карточку сторож не завёл — заводим как штатный ответ:
остановка цепочки (skip replied) + push_warm_lead с адресом ответившего.   lid_natruli.py [primenit]"""
import json, sqlite3, sys
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config
from sender.leaddesk import LeadDesk
from sender.store import Store
from sender.dtos import EventIn
БАЗА = r"C:\sender\sender.db"; РИД = 17770; КАМП = 14; ОТ = "giga004@mail.ru"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True); c.row_factory = sqlite3.Row
print("лиды получателя:", [dict(x) for x in c.execute("SELECT id, reply_kind, status FROM leads WHERE recipient_id=?", (РИД,))])
д = json.loads(c.execute("SELECT detail_json FROM events WHERE id=446320").fetchone()[0]); c.close()
текст = " ".join(str(д.get("snippet") or "").split())
print("текст:", текст[:200])
if "primenit" not in sys.argv: raise SystemExit("вхолостую")
cfg = Config.load(r"C:\sender\sender.yaml"); store = Store(БАЗА)
store.append_event(EventIn(dedup_key="imap:1785209194:119:other:stop_chain", event_type="skip", event_ts=datetime.now(timezone.utc),
                           recipient_id=РИД, campaign_id=КАМП, detail={"reason": "replied"}))
рек = store.get_recipient(РИД)
lid = LeadDesk(cfg, store).push_warm_lead(рек, "", "[вопрос] " + текст[:3000], otvetil=ОТ)
print("карточка лида:", lid)
