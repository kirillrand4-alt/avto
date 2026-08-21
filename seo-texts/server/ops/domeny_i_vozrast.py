# -*- coding: utf-8 -*-
"""Наши домены-отправители: возраст, ящики, отправка и отказы по каждому.

Владелец спрашивает, можно ли взять домены, с которых слали год назад.
Прежде чем отвечать, надо знать, что у нас вообще есть: какие домены сейчас
в конфиге, что известно про их регистрацию (gates.young_domain.domains) и
как они себя ведут.
"""
import sqlite3
import sys
from collections import Counter
from datetime import date

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
ящики = list(cfg.mailboxes())
по_домену = {}
for mb in ящики:
    д = mb.mailbox_id.split("@")[-1].lower()
    по_домену.setdefault(д, {"ящики": 0, "напр": mb.division})
    по_домену[д]["ящики"] += 1

даты = cfg.get("gates.young_domain.domains", {}) or {}
мин = cfg.get("gates.young_domain.min_age_days", 0)
print(f"порог молодого домена: {мин} дней; дат в конфиге: {len(даты)}")

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ушло = Counter(str(р["mailbox_id"] or "").split("@")[-1].lower()
               for р in c.execute(
                   "SELECT mailbox_id FROM messages WHERE status='sent'"))
отбивки = Counter(str(р["mailbox_id"] or "").split("@")[-1].lower()
                  for р in c.execute(
                      "SELECT mailbox_id FROM events WHERE event_type='bounce'"))

print(f"\n{'домен':<30} {'напр':<6} {'ящиков':>7} {'зарег.':<12} {'возраст':>8} "
      f"{'ушло':>7} {'отбивок':>8}")
сегодня = date.today()
for д in sorted(по_домену):
    инфо = по_домену[д]
    рег = str(даты.get(д, "")) if даты else ""
    возраст = ""
    if рег:
        try:
            г, м, дн = (int(x) for x in рег.split("-"))
            возраст = str((сегодня - date(г, м, дн)).days) + " дн"
        except Exception:                                          # noqa: BLE001
            возраст = "?"
    print(f"{д:<30} {str(инфо['напр']):<6} {инфо['ящики']:>7} {рег:<12} "
          f"{возраст:>8} {ушло.get(д, 0):>7} {отбивки.get(д, 0):>8}")

# домены, с которых слали когда-либо, но которых уже нет в конфиге
жили = {str(р["mailbox_id"] or "").split("@")[-1].lower()
        for р in c.execute("SELECT DISTINCT mailbox_id FROM messages "
                           "WHERE mailbox_id IS NOT NULL")}
чужие = sorted(жили - set(по_домену) - {""})
print(f"\nдомены, с которых слали, но которых нет в конфиге: {чужие or 'нет'}")
