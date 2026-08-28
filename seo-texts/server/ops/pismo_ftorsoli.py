# -*- coding: utf-8 -*-
"""Письмо на адрес, который компания назвала сама: soli@ftorsoli.ru.

Лид: «Все предложения пишите на soli@ftorsoli.ru — С уважением, Кулиш».
Как и с virtex-food.ru, это не холодный контакт, а письмо по приглашению:
потолок адресов на компанию обходим осознанно и пишем это в причине.
Ящик отправки прибиваем к тому, с которого шла переписка.
"""
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
ИНН = "5908047203"
АДРЕС = "soli@ftorsoli.ru"

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("=== что уже писали этой компании ===")
for r in c.execute(
        "SELECT m.id, m.status, m.sent_at, m.mailbox_id, rc.email "
        "  FROM messages m JOIN recipients rc ON rc.id=m.recipient_id "
        " WHERE rc.inn=? ORDER BY m.sent_at", (ИНН,)):
    print("   msg %-6s %-9s %s  %-28s ящик %s"
          % (r["id"], r["status"], str(r["sent_at"])[:16],
             str(r["email"])[:28], str(r["mailbox_id"])[:34]))
исход = c.execute(
    "SELECT cr.subject, cr.body, cr.panel_json, cr.campaign_id, cr.recipient_id, "
    "       m.mailbox_id, m.sent_at "
    "  FROM confirm_reviews cr JOIN messages m ON m.id = cr.message_id "
    " WHERE cr.inn=? AND m.status='sent' AND COALESCE(cr.body,'')<>'' "
    " ORDER BY m.sent_at DESC LIMIT 1", (ИНН,)).fetchone()
c.close()
if исход is None:
    print("исходного письма не нашлось")
    raise SystemExit(1)
print("")
print("берём письмо от %s, ящик %s" % (str(исход["sent_at"])[:16], исход["mailbox_id"]))
тело = str(исход["body"] or "")
# ОБРАЩЕНИЕ СНИМАЕМ. В исходном письме «Добрый день, Оксана Николаевна!» —
# это Кулиш, а soli@ общий ящик компании: обращаться там по имени значит
# писать не тому человеку.
_стр = тело.split("\n")
import re as _re
if _стр and _re.match(r"(?i)^\s*(добрый день|здравствуйте|доброе утро|добрый вечер)",
                      _стр[0]):
    print("приветствие: %r -> 'Добрый день!'" % _стр[0])
    _стр[0] = "Добрый день!"
    тело = "\n".join(_стр)
print("ТЕМА: %s" % исход["subject"])
print("-" * 60)
print(тело[:700])
print("-" * 60)
if not КАТИТЬ:
    raise SystemExit(0)

from datetime import datetime, timezone                           # noqa: E402
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.dtos import RecipientIn                               # noqa: E402
from sender.ai_quota import build_ai_quota                        # noqa: E402
from sender.auto_send import next_slot, recipient_tz_name, window_from  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
стар = store.get_recipient(int(исход["recipient_id"]))
rid = store.upsert_recipient(RecipientIn(
    email=АДРЕС, domain=АДРЕС.split("@", 1)[1], inn=ИНН,
    company_name=getattr(стар, "company_name", None),
    okved=getattr(стар, "okved", None), segment=getattr(стар, "segment", None),
    source="adres_nazvala_kompaniya",
    region=getattr(стар, "region", None), tz=getattr(стар, "tz", None),
    extra={"po_priglasheniyu": True,
           "pochemu": "компания сама назвала адрес в ответе"}))
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
# ЯЩИК ПРИБИВАЕМ: письмо продолжает ту же переписку, отвечать должен тот же
# менеджер, а не любой свободный из направления.
панель["mailbox_id"] = исход["mailbox_id"]
панель["po_priglasheniyu"] = {
    "adres_nazvala": "o.kulish@ftorsoli.ru",
    "zametka": "«Все предложения пишите на soli@ftorsoli.ru» — Кулиш"}
rev, создано = store.confirm_submit(
    email=АДРЕС, subject=исход["subject"], body=тело, inn=ИНН,
    campaign_id=int(исход["campaign_id"]), recipient_id=rid, message_id=mid,
    panel=панель,
    reason="копия на второй адрес: адрес назвала сама компания")
print("карточка: %d (создана: %s), ящик в карточке: %s"
      % (rev, создано, исход["mailbox_id"]))
win = window_from(store, cfg)
rec = store.get_recipient(rid)
слот = next_slot(win, recipient_tz_name(win, rec), datetime.now(timezone.utc))
store.reschedule_message(int(mid), слот)
ок = store.confirm_decide(
    rev, status="approved", decided_by="адрес назвала компания",
    reason="копия на второй адрес: адрес назвала сама компания")
print("в автоотправку: %s, слот %s" % (ок, слот))
