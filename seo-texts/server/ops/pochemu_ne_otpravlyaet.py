# -*- coding: utf-8 -*-
"""Почему автоотправка стоит: настройка, окно, слоты, ящики.

Проверяем по порядку то, что реально останавливает цикл: включён ли он в
настройках, идёт ли окно отправки сейчас, на какое время назначены
письма и готовы ли ящики (пауза, рамп, дневной лимит).
"""
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.auto_send import ENABLED_KEY, window_from                 # noqa: E402
from sender.company_card import CompanyCards                          # noqa: E402
from sender.config import Config                                      # noqa: E402
from sender.gates import Gates                                        # noqa: E402
from sender.sender import Sender                                      # noqa: E402
from sender.store import Store                                        # noqa: E402
from sender.suppression import Suppression                            # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
snd = Sender(cfg, store, Suppression(store), Gates(cfg, store), dry_run=True,
             cards=CompanyCards(
                 index_path=str(cfg.get("obzvon.index_path", "") or "") or None,
                 enrich_db_path=str(cfg.get("obzvon.enrich_db", "") or "")
                 or None))
сейчас = datetime.now(timezone.utc)
print(f"сейчас UTC: {сейчас.isoformat()[:19]}")

вкл = store.get_setting(ENABLED_KEY)
print(f"\n1) НАСТРОЙКА автоотправки: {вкл!r}")

окно = window_from(store, cfg)
print(f"\n2) ОКНО ОТПРАВКИ: {окно}")

with store._lock:
    строки = store._conn.execute(
        "SELECT m.id, m.campaign_id, m.status, m.scheduled_at "
        "  FROM messages m JOIN confirm_reviews cr ON cr.message_id=m.id "
        " WHERE m.status IN ('scheduled','sending') "
        "   AND cr.status IN ('approved','edited') "
        " ORDER BY m.scheduled_at").fetchall()
print(f"\n3) ПИСЕМ ЖДЁТ: {len(строки)}")
если_пора = [с for с in строки if str(с[3] or "") <= сейчас.isoformat()]
print(f"   срок наступил у {len(если_пора)}")
по_камп = Counter(str(с[1]) for с in строки)
print(f"   по кампаниям: {dict(по_камп)}")
for с in строки[:5]:
    print(f"   письмо #{с[0]} камп {с[1]} {с[2]} слот {str(с[3])[:19]}")
if строки:
    print(f"   самый ранний слот: {str(строки[0][3])[:19]}")
    print(f"   самый поздний слот: {str(строки[-1][3])[:19]}")

print("\n4) ЯЩИКИ:")
for mb in cfg.mailboxes():
    div = str(getattr(mb, "division", "") or "").lower()
    if not ("meyer" in div or "мейер" in div):
        continue
    try:
        r = snd.mailbox_readiness(mb.mailbox_id)
    except Exception as ex:                                        # noqa: BLE001
        print(f"   {mb.mailbox_id}: ОШИБКА {type(ex).__name__} {ex}")
        continue
    print(f"   {mb.mailbox_id:38} лимит {r.daily_limit:>4} "
          f"ушло {r.sent_today:>4} пауза={r.paused} "
          f"причины={list(r.reasons or ())[:3]}")
