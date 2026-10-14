# -*- coding: utf-8 -*-
"""Компании с вердиктом «кц» в базе «наш или нет»: выручка, отрасли, источник
решения + выборка на независимого судью (opus): подходит ли им компрессорное
оборудование (компрессоры, осушители, генераторы азота/кислорода, пневмоинструмент).

    kc_vyruchka_i_proverka.py [n=40]
"""
import json
import os
import random
import re
import sqlite3
import sys
from collections import Counter

os.environ.setdefault("PROVIDER_THINKING_FIELD", "omit")
sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.review_lenses import default_caller  # noqa: E402
from sender.store import Store  # noqa: E402

N = int(dict(а.split("=", 1) for а in sys.argv[1:] if "=" in а).get("n", "40"))
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
e.row_factory = sqlite3.Row
кц = [dict(р) for р in e.execute("SELECT inn, name, revenue_rub, revenue_year, okved, verdikt_istochnik "
                                  "FROM companies WHERE verdikt_napr='кц'")]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
сег = {str(i): s for i, s in c.execute("SELECT inn, segment FROM recipients WHERE inn IS NOT NULL")}


def корз(в):
    try:
        в = float(в or 0)
    except (TypeError, ValueError):
        в = 0
    if в <= 0:
        return "0) нет данных"
    for порог, имя in ((10e6, "1) до 10 млн"), (100e6, "2) 10-100 млн"), (500e6, "3) 100-500 млн"),
                       (2e9, "4) 0.5-2 млрд")):
        if в < порог:
            return имя
    return "5) от 2 млрд"


print("всего «кц»: %d" % len(кц))
print("выручка:", dict(sorted(Counter(корз(к["revenue_rub"]) for к in кц).items())))
print("источник решения:", dict(Counter(к["verdikt_istochnik"] for к in кц).most_common()))
print("отрасль книги:", dict(Counter((сег.get(к["inn"]) or "?")[:24] for к in кц).most_common(12)))

cfg = Config.load(r"C:\sender\sender.yaml")
q = build_ai_quota(Store(cfg.get("service.db_path", r"C:\sender\sender.db")), cfg)
random.seed(14)
выб = random.sample(кц, min(N, len(кц)))
блоки = []
for k, к in enumerate(выб):
    d = q._site_facts(к["inn"]) or {}
    п = "; ".join("%s: %s" % (кл, (v if isinstance(v, str) else ", ".join(map(str, v)))[:180])
                  for кл, v in d.items() if v and кл in ("продукция", "сырьё", "оборудование_линии", "масштаб"))
    блоки.append("=== %d | %s | ОКВЭД %s | выручка %s\n%s" % (k, к["name"], к["okved"], корз(к["revenue_rub"]),
                                                               п[:600] or "(паспорта нет)"))
ПРОМПТ = ("Ты инженер по продаже компрессорного оборудования: винтовые и поршневые компрессоры, осушители и "
          "фильтры сжатого воздуха, генераторы азота и кислорода, пневмоинструмент. По карточке каждой компании "
          "реши, нужен ли ей сжатый воздух/азот/кислород в работе (цех, производство, стройка, ремонт, покраска, "
          "техника, упаковка). Офис, торговля без склада и цеха, услуги, IT - не покупатель.\n"
          "Ответ строго JSON: {\"r\":[{\"id\":N,\"kc\":\"да|нет|сомнительно\",\"pochemu\":\"до 10 слов\"}]}\n\n")
ответ, _ = default_caller(ПРОМПТ + "\n\n".join(блоки), max_tokens=5000, model="claude-opus-4-8")
д = json.loads(re.search(r"\{.*\}", ответ, re.S).group(0))
print("судья opus по %d «кц»: %s" % (len(выб), dict(Counter(р.get("kc") for р in д.get("r") or []))))
for р in д.get("r") or []:
    if р.get("kc") != "да":
        к = выб[int(р["id"])]
        print("   %s: %s [%s] — %s" % (р.get("kc"), str(к["name"])[:36], корз(к["revenue_rub"]), р.get("pochemu")))
print("=== КЦ: ВЫРУЧКА И ПРОВЕРКА ===")
