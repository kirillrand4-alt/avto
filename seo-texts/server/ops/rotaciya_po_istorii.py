# -*- coding: utf-8 -*-
"""Работает ли ротация ящиков - по фактически отправленным письмам Meyer.

Проба pick_mailbox ротацию показать не может: круг двигает указатель
«последний реально отправленный», а проба не шлёт. Зато история отправок
показывает ровно то, что спрашивает владелец.
"""
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

напр = {}
for mb in cfg.mailboxes():
    напр[str(getattr(mb, "mailbox_id", ""))] = str(
        getattr(mb, "division", "") or "?")

for окно, дней in (("за 7 дней", 7), ("за 30 дней", 30)):
    с = Counter()
    with store._lock:
        for р in store._conn.execute(
                "SELECT mailbox_id FROM messages "
                " WHERE status='sent' AND campaign_id=11 "
                "   AND sent_at >= datetime('now', ?)", ("-%d days" % дней,)):
            с[str(р["mailbox_id"] or "не задан")] += 1
    print("--- Meyer (кампания 11), отправлено %s: %d писем с %d ящиков ---"
          % (окно, sum(с.values()), len([k for k in с if "@" in k])))
    for к, в in с.most_common(8):
        print("   %-42s %5d  напр=%s" % (к[:42], в, напр.get(к, "?")))
    print("")

# ящики Meyer и их дневные лимиты - потолок партии за сутки
мейер = [mb for mb in cfg.mailboxes()
         if str(getattr(mb, "division", "")).lower() == "meyer"]
лимит = 0
for mb in мейер:
    л = getattr(mb, "daily_limit", None) or getattr(mb, "limit_per_day", None)
    лимит += int(л or 0)
print("=" * 74)
print("=== ЯЩИКИ MEYER ===")
print("всего ящиков Meyer: %d; суммарный дневной лимит: %s"
      % (len(мейер), лимит or "в конфиге не задан"))
пулы = dict(cfg.provider_pools() or {})
for имя, сп in пулы.items():
    м = sum(1 for x in сп if напр.get(str(x), "") == "meyer")
    print("   пул %-14s ящиков %2d, из них Meyer %2d" % (имя, len(сп), м))
