# -*- coding: utf-8 -*-
"""Возраст доменов-отправителей и что о них думает гейт молодых доменов.

Даты регистрации живут в конфиге (gates.young_domain.domains) — их туда
кладут из whois. Домен, которого в списке нет, гейт считает ЗРЕЛЫМ, и это
дыра: новый домен молча сводит заслон на нет. Поэтому показываем и такие.
"""
import sys
from collections import defaultdict
from datetime import date, datetime

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
порог = int(cfg.get("gates.young_domain.min_age_days", 0) or 0)
сырое = dict(cfg.get("gates.young_domain.domains", None) or {})
провайдеры = cfg.get("gates.young_domain.providers", None) or ("other", "unknown")

# Ящики по доменам, чтобы видеть вес каждого домена.
ящики = defaultdict(list)
for mb in cfg.mailboxes():
    адрес = str(getattr(mb, "email", "") or getattr(mb, "mailbox_id", ""))
    дом = адрес.split("@")[-1].strip().lower()
    напр = str(getattr(mb, "division", "") or "").lower()
    ящики[дом].append((адрес, "Meyer" if "meyer" in напр or "мейер" in напр
                       else "КЦ"))

сегодня = date.today()
print(f"порог гейта: {порог} дней | держим получателей на {tuple(провайдеры)}")
print(f"\n{'домен':<32} {'создан':<12} {'дней':>5} {'ящиков':>7}  состояние")
строки = []
for дом in sorted(set(list(сырое) + list(ящики))):
    д = сырое.get(дом)
    if д:
        try:
            создан = datetime.fromisoformat(str(д)[:10]).date()
            дней = (сегодня - создан).days
        except Exception:                                        # noqa: BLE001
            создан, дней = None, None
    else:
        создан, дней = None, None
    n = len(ящики.get(дом, []))
    if дней is None:
        сост = "ДАТЫ НЕТ — гейт считает зрелым"
    elif порог and дней < порог:
        сост = f"молодой, созреет через {порог - дней} дн."
    else:
        сост = "зрелый"
    строки.append((дней if дней is not None else -1, дом, создан, дней, n, сост))

for _, дом, создан, дней, n, сост in sorted(строки):
    print(f"{дом:<32} {str(создан or '—'):<12} "
          f"{(дней if дней is not None else '—'):>5} {n:>7}  {сост}")

всего = sum(len(v) for v in ящики.values())
без_даты = sum(1 for _, дом, _c, д, _n, _s in строки
               if д is None and ящики.get(дом))
print(f"\nящиков всего: {всего} | доменов: {len(ящики)} | "
      f"из них без даты в конфиге: {без_даты}")
