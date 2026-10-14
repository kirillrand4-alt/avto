# -*- coding: utf-8 -*-
"""«кц» внутри группы «Россия 9000»: отрасли книги, ОКВЭД-классы, выручка +
независимый судья (opus) по выборке: нужен ли сжатый воздух (КЦ) и подходит ли
хоть один станок Meyer. Владелец 14.10: «это чаще всего именно кц? мейер никаким боком?»

    kc_v_9000_razbor.py [n=40]
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
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
верд = {str(r[0]): r[1] for r in e.execute("SELECT inn, verdikt_napr FROM companies")}
окв = {str(r[0]): (r[1] or "") for r in e.execute("SELECT inn, okved FROM companies")}
выр = {str(r[0]): r[1] or 0 for r in e.execute("SELECT inn, revenue_rub FROM companies")}
имя = {str(r[0]): r[1] for r in e.execute("SELECT inn, name FROM companies")}
сег = {}
for inn, s in c.execute("SELECT inn, segment FROM recipients WHERE extra_json LIKE '%Россия 9000%'"):
    сег.setdefault(str(inn), s or "?")
кц = [i for i in сег if верд.get(i) == "кц"]
print("«кц» в «Россия 9000»: %d" % len(кц))
print("отрасль книги:")
for k, n in Counter(сег[i] for i in кц).most_common(14):
    print("   %-38s %d" % (k[:38], n))
print("ОКВЭД (2 знака):", dict(Counter(окв.get(i, "")[:2] or "?" for i in кц).most_common(12)))


def корз(в):
    try:
        в = float(в or 0)
    except (TypeError, ValueError):
        в = 0
    return "нет" if в <= 0 else "<100млн" if в < 1e8 else "<1млрд" if в < 1e9 else ">1млрд"


print("выручка:", dict(Counter(корз(выр.get(i)) for i in кц)))
cfg = Config.load(r"C:\sender\sender.yaml")
q = build_ai_quota(Store(cfg.get("service.db_path", r"C:\sender\sender.db")), cfg)
random.seed(21)
выб = random.sample(кц, min(N, len(кц)))
блоки = []
for k, i in enumerate(выб):
    d = q._site_facts(i) or {}
    п = "; ".join("%s: %s" % (кл, (v if isinstance(v, str) else ", ".join(map(str, v)))[:160])
                  for кл, v in d.items() if v and кл in ("продукция", "сырьё", "оборудование_линии", "упаковка_фасовка"))
    блоки.append("=== %d | %s | ОКВЭД %s | отрасль %s\n%s" % (k, имя.get(i), окв.get(i), сег.get(i), п[:550] or "(паспорта нет)"))
ПР = ("Две оценки по каждой компании.\n"
      "KC: нужен ли ей сжатый воздух/азот/кислород в работе (цех, производство, карьер, стройка, ремонт, "
      "упаковка, пневмоавтоматика). Офис, торговля без склада, услуги - нет.\n"
      "MEYER: подходит ли ей хоть один станок Meyer - ФОТОСЕПАРАТОР (сыпучий поток: зерно, крупы, семена, "
      "орехи, ягоды, овощи, кофе, специи; а также переработка пластика во флексу/гранулу, стеклобой, "
      "кварц/известняк/соль, щепа) или РЕНТГЕН упакованного пищевого продукта (мясо, молочка, кондитерка, "
      "снеки, готовая еда).\n"
      "Ответ строго JSON: {\"r\":[{\"id\":N,\"kc\":\"да|нет|сомн\",\"meyer\":\"да|нет|сомн\","
      "\"pochemu\":\"до 10 слов\"}]}\n\n")
ответ, _ = default_caller(ПР + "\n\n".join(блоки), max_tokens=6000, model="claude-opus-4-8")
д = json.loads(re.search(r"\{.*\}", ответ, re.S).group(0))
r = д.get("r") or []
print("судья opus по %d «кц»: КЦ %s | Meyer %s" % (len(выб), dict(Counter(x.get("kc") for x in r)),
                                                  dict(Counter(x.get("meyer") for x in r))))
for x in r:
    if x.get("meyer") in ("да", "сомн") or x.get("kc") != "да":
        i = выб[int(x["id"])]
        print("   КЦ:%s Meyer:%s | %s [%s] — %s" % (x.get("kc"), x.get("meyer"), str(имя.get(i))[:34],
                                                 str(сег.get(i))[:18], x.get("pochemu")))
print("=== КЦ В 9000: РАЗБОР ===")
