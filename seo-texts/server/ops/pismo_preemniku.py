# -*- coding: utf-8 -*-
"""То же письмо преемнику, с обращением по имени.

Владелец 28.08: автоответ «я закончила работу в компании, обращения
направляйте Пушиной Александре Вячеславовне <pav4@virtex-food.ru>» —
пишем ей то же письмо, но персонифицированно.

Это НЕ холодный третий контакт, а письмо по приглашению: компания сама
назвала, к кому обращаться. Поэтому кладём в очередь напрямую, минуя
потолок «двух адресов на компанию», и пишем это в причине карточки.
"""
import json
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
ИНН = "5445014374"
АДРЕС = "pav4@virtex-food.ru"
ФИО = "Пушина Александра Вячеславовна"
ОБРАЩЕНИЕ = "Александра Вячеславовна"

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
исход = c.execute(
    "SELECT cr.id, cr.subject, cr.body, cr.panel_json, cr.campaign_id, "
    "       cr.recipient_id, cr.email, m.sent_at "
    "  FROM confirm_reviews cr JOIN messages m ON m.id = cr.message_id "
    " WHERE cr.inn=? AND m.status='sent' AND COALESCE(cr.body,'')<>'' "
    " ORDER BY m.sent_at DESC LIMIT 1", (ИНН,)).fetchone()
if исход is None:
    print("исходного письма не нашлось")
    raise SystemExit(1)
print("берём письмо от %s, ушло на %s" % (str(исход["sent_at"])[:16], исход["email"]))
тело = str(исход["body"] or "")
строки = тело.split("\n")
было = строки[0]
строки[0] = "Добрый день, %s!" % ОБРАЩЕНИЕ
тело = "\n".join(строки)
print("приветствие: %r -> %r" % (было, строки[0]))
print("")
print("ТЕМА: %s" % исход["subject"])
print("-" * 60)
print(тело[:900])
print("-" * 60)
c.close()
if not КАТИТЬ:
    raise SystemExit(0)

from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.dtos import RecipientIn                               # noqa: E402
from sender.ai_quota import build_ai_quota                        # noqa: E402
from sender.auto_send import next_slot, recipient_tz_name, window_from  # noqa: E402
from datetime import datetime, timezone                           # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
стар = store.get_recipient(int(исход["recipient_id"]))
rid = store.upsert_recipient(RecipientIn(
    email=АДРЕС, domain=АДРЕС.split("@", 1)[1], inn=ИНН,
    company_name=getattr(стар, "company_name", None),
    okved=getattr(стар, "okved", None), segment=getattr(стар, "segment", None),
    contact_name=ФИО, source="preemnik_po_avtootvetu",
    region=getattr(стар, "region", None), tz=getattr(стар, "tz", None),
    extra={"preemnik": True, "iz_lida": 223,
           "pochemu": "компания сама назвала контакт в автоответе"}))
print("получатель: %d" % rid)
mid, _sid, почему = q._ensure_message(int(исход["campaign_id"]), rid)
if mid is None:
    print("письмо не завелось: %s" % почему)
    raise SystemExit(1)
try:
    панель = json.loads(исход["panel_json"] or "{}") or {}
except Exception:                                                # noqa: BLE001
    панель = {}
панель["email"] = АДРЕС
панель["recipient_id"] = rid
панель["preemnik"] = {"fio": ФИО, "iz_lida": 223,
                      "zametka": "адрес назвала сама компания в автоответе"}
# НАПРЯМУЮ, минуя Confirm.submit: его потолок «двух адресов на компанию»
# режет третье письмо, а это не холодный контакт, а ответ на приглашение.
rev, создано = store.confirm_submit(
    email=АДРЕС, subject=исход["subject"], body=тело, inn=ИНН,
    campaign_id=int(исход["campaign_id"]), recipient_id=rid, message_id=mid,
    panel=панель,
    reason="копия на второй адрес: контакт назвала сама компания (лид 223)")
print("карточка: %d (создана: %s)" % (rev, создано))
win = window_from(store, cfg)
rec = store.get_recipient(rid)
слот = next_slot(win, recipient_tz_name(win, rec), datetime.now(timezone.utc))
store.reschedule_message(int(mid), слот)
ок = store.confirm_decide(
    rev, status="approved", decided_by="преемник по автоответу",
    reason="копия на второй адрес: контакт назвала сама компания (лид 223)")
print("в автоотправку: %s, слот %s" % (ок, слот))
