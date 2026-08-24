# -*- coding: utf-8 -*-
"""Из чего состоит статический префикс письма — что можно урезать.

Префикс — 70.7% всего входа, и половина писем платит за него полную цену
(попадание в тёплый кэш зависит от того, на какой канал шлюза попал вызов).
Значит его размер стоит денег напрямую. Разбираем по кускам.
"""
import sys

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

import gen_provider                                            # noqa: E402
from sender.ai_letter import (RULES_BY_DIVISION, facts_block,  # noqa: E402
                              gen_prompt, load_facts, _GEN_HEAD)
from sender.ai_quota import build_ai_quota                     # noqa: E402
from sender.config import Config                               # noqa: E402
from sender.store import Store                                 # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
факты = load_facts(division="kc")
группы = store.recipient_groups().get("по_id") or {}
rid = next((r for r, gr in sorted(группы.items()) if "Партия 935" in gr), None)
req = q._request(store.get_recipient(rid))
сис, тело = gen_provider.razrezat_promt(gen_prompt([req], факты, "kc"))

куски = [
    ("шапка (_GEN_HEAD)", _GEN_HEAD.get("kc", "")),
    ("правила (RULES_BY_DIVISION)", RULES_BY_DIVISION.get("kc", "")),
    ("факты (facts_block)", facts_block(факты, "kc")),
]
print("статический префикс: %d знаков (~%d токенов)" % (len(сис), len(сис) // 1.8))
print("переменная часть (карточка компании): %d знаков\n" % len(тело))
учтено = 0
for имя, текст in куски:
    д = 100.0 * len(текст) / len(сис) if сис else 0
    учтено += len(текст)
    print("  %-30s %7d знаков  %5.1f%%  %s"
          % (имя, len(текст), д, "#" * int(д / 3)))
print("  %-30s %7d знаков  %5.1f%%" % ("прочее (склейка, формат)",
                                       len(сис) - учтено,
                                       100.0 * (len(сис) - учтено) / len(сис)))

print("\n=== ЧТО В БЛОКЕ ФАКТОВ (строки верхнего уровня) ===")
фб = facts_block(факты, "kc")
строк = фб.split("\n")
print("  строк: %d" % len(строк))
for с in строк[:4]:
    print("  | %s" % с[:130])
print("  | …")
пункты = [с for с in строк if с.strip().startswith("-")]
print("  пунктов-перечислений: %d, средняя длина %d знаков"
      % (len(пункты), (sum(len(с) for с in пункты) // len(пункты)) if пункты else 0))
print("  самый длинный пункт: %d знаков" % max((len(с) for с in пункты), default=0))
