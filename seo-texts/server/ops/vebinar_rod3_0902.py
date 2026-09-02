# -*- coding: utf-8 -*-
"""Только чтение: переписывает ли движок «был/решил/хотел» в женский род."""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
import sender.gender_agree as GA  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
ящики = {m["mailbox_id"]: m for m in cfg.get("mailboxes", [])}

куски = [
    "Я был среди спикеров, мы с коллегами рассказывали о современных "
    "технологиях контроля качества на пищевых производствах.",
    "Я тоже выступал на нём, мы с коллегами разбирали современные технологии.",
    "После вебинара решил отдельно связаться с участниками.",
    "Хотел продолжить разговор точечно и понять, какие задачи стоят у вас.",
    "Готов разобрать ваши задачи и найти решение.",
    "Я был среди выступавших, тему мы разбирали вместе с коллегами.",
]
for mid in ("i.kuznetsova@sort-systems.ru", "a.tyunin@sort-systems.ru"):
    m = ящики[mid]
    print("=== %s (%s) ===" % (m.get("from_name"), GA.gender_of(m.get("from_name", ""))))
    for к in куски:
        r = GA.agree_for_mailbox(к, m.get("from_name", ""), cfg, mid)
        знак = "изменено" if r != к else "как есть"
        print("  [%s] %s" % (знак, r[:96]))
    print()
