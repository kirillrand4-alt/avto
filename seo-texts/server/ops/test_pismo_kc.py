# -*- coding: utf-8 -*-
"""Сколько компаний группы «Россия 9000» признано КЦ + ТЕСТОВОЕ письмо КЦ
(владелец 14.10). Письмо НЕ ставится в очередь — только текст на экран и в
_ops/test-pismo-kc.json. Кандидаты: вердикт «кц», нет активной сделки КЦ,
самый подробный паспорт и выручка от 100 млн.

    test_pismo_kc.py [n=1]
"""
import io
import json
import os
import sqlite3
import sys
from collections import Counter

os.environ.setdefault("PROVIDER_THINKING_FIELD", "omit")
sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
import gen_provider  # noqa: E402
from sender.ai_letter import AiLetterGen, load_facts  # noqa: E402
from sender.ai_quota import build_ai_quota  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.sdelki_napr import blok  # noqa: E402
from sender.store import Store  # noqa: E402

N = int(dict(а.split("=", 1) for а in sys.argv[1:] if "=" in а).get("n", "1"))
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
верд = {str(r[0]): (r[1], r[2]) for r in e.execute("SELECT inn, verdikt_napr, verdikt_istochnik FROM companies")}
выр = {str(r[0]): r[1] or 0 for r in e.execute("SELECT inn, revenue_rub FROM companies")}
группа = {}
for rid, inn in c.execute("SELECT id, inn FROM recipients WHERE extra_json LIKE '%Россия 9000%'"):
    группа.setdefault(str(inn), rid)
св = Counter((верд.get(i) or (None, None))[0] or "нет вердикта" for i in группа)
ист = Counter((верд.get(i) or (None, None))[1] for i in группа if (верд.get(i) or (None,))[0] == "кц")
print("компаний в «Россия 9000»: %d; вердикты: %s" % (len(группа), dict(св.most_common())))
print("из них «кц» по источнику решения: %s" % dict(ист))

канд = []
for inn, rid in группа.items():
    if (верд.get(inn) or (None,))[0] != "кц" or blok(c, inn, "kc"):
        continue
    if float(выр.get(inn) or 0) < 1e8:
        continue
    d = q._site_facts(inn) or {}
    поля = sum(1 for k in ("продукция", "сырьё", "оборудование_линии", "масштаб", "мощности", "цитата") if d.get(k))
    канд.append((поля, float(выр.get(inn) or 0), rid, inn))
канд.sort(reverse=True)
print("кандидатов КЦ с выручкой от 100 млн и без сделки КЦ: %d" % len(канд))

ЦЕНЫ = {"in": 0, "out": 0}


def caller(prompt, *a, **k):
    системный, тело = gen_provider.razrezat_promt(prompt)
    m = gen_provider._raw_stream([{"role": "user", "content": тело}], "claude-sonnet-4-6", 6000,
                                 thinking=False, effort="low", system=системный)
    u = getattr(m, "usage", None)
    ЦЕНЫ["in"] += int(getattr(u, "input_tokens", 0) or 0)
    ЦЕНЫ["out"] += int(getattr(u, "output_tokens", 0) or 0)
    return "".join(b.text for b in m.content if getattr(b, "type", "") == "text")


# разные отрасли: лучший кандидат каждой отрасли книги
сег = {str(i): s_ for i, s_ in c.execute("SELECT inn, segment FROM recipients WHERE extra_json LIKE '%Россия 9000%'")}
выбор, были = [], set()
for x in канд:
    о = сег.get(x[3]) or "?"
    if о not in были:
        были.add(о)
        выбор.append(x)
итог = []
for поля, в, rid, inn in выбор[:N]:
    rec = store.get_recipient(rid)
    req = q._request(rec)
    req["target_division"] = "kc"
    req.setdefault("extra", {})["angle_shift"] = rid
    try:
        q._add_ideas_generic([req])
    except Exception as ex:  # noqa: BLE001
        print("идеи не раздались:", str(ex)[:80])
    res = AiLetterGen(caller, facts_by_division={"kc": load_facts(division="kc")}, best_of=1,
                      checker=caller).generate([req])
    L = res.ok.get(0)
    брак = res.rejected.get(0)
    черн = res.drafts.get(0) if hasattr(res, "drafts") else None
    з = {"inn": inn, "компания": rec.company_name, "email": rec.email, "выручка": в, "поля_паспорта": поля,
         "ok": bool(L), "брак": брак, "тема": (L or черн or {}).get("subject"), "тело": (L or черн or {}).get("body")}
    итог.append(з)
    print("\n=== %s | ИНН %s | %s | выручка %.0f млн | полей паспорта %d" % (rec.company_name, inn, rec.email, в / 1e6, поля))
    print("ГОДНО" if L else "БРАК: %s" % брак)
    print("Тема: %s\n\n%s" % (з["тема"], з["тело"]))
json.dump(итог, io.open(r"C:\sender\_ops\test-pismo-kc.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\nтокены: вход %d, выход %d" % (ЦЕНЫ["in"], ЦЕНЫ["out"]))
print("=== ТЕСТ ПИСЬМА КЦ ===")
