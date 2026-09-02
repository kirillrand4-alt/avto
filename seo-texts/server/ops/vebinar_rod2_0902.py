# -*- coding: utf-8 -*-
"""Только чтение: боевая проверка согласования рода на предложенной концовке."""
import inspect
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config     # noqa: E402
import sender.gender_agree as GA     # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
хвост_м = ("Подскажите, как сейчас на вашем производстве работают с посторонними "
           "включениями? Используете металлодетектор, рентген или оптический "
           "сортировщик? Готов разобрать ваши задачи и предложить решение.")
хвост_ж = хвост_м.replace("Готов ", "Готова ")

ящики = {m["mailbox_id"]: m for m in cfg.get("mailboxes", [])}
проба = ["i.kuznetsova@sort-systems.ru", "a.tyunin@sort-systems.ru",
         "a.miroshnichenko@optic-sort.ru", "v.ivanov@optic-sort.ru"]

print("=== ЕСЛИ НАПИСАТЬ «Готов» (мужская форма, как велит канон) ===")
for mid in проба:
    m = ящики.get(mid, {})
    r = GA.agree_for_mailbox(хвост_м, m.get("from_name", ""), cfg, mid)
    print("  %-32s %-30s -> «%s»"
          % (mid, m.get("from_name", "")[:30], r.split("? ")[-1][:46]))

print("\n=== ЕСЛИ НАПИСАТЬ «Готова» (женская форма) ===")
for mid in проба:
    m = ящики.get(mid, {})
    r = GA.agree_for_mailbox(хвост_ж, m.get("from_name", ""), cfg, mid)
    плохо = "Готова" in r and GA.gender_of(m.get("from_name", "")) != "f"
    print("  %-32s %-30s -> «%s» %s"
          % (mid, m.get("from_name", "")[:30], r.split("? ")[-1][:46],
             "<-- НЕВЕРНЫЙ РОД" if плохо else ""))

print("\n=== ПОЛ ЯЩИКОВ MEYER ===")
for m in cfg.get("mailboxes", []):
    if str(m.get("division")) == "meyer":
        print("  %-34s %-30s пол=%s" % (m["mailbox_id"], m.get("from_name", "")[:30],
                                        GA.gender_of(m.get("from_name", ""))))
