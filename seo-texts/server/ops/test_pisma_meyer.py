# -*- coding: utf-8 -*-
"""Тестовые письма Meyer по канону редактора 15.10 — по одному на отрасль:
кондитерка, мясо, зерно, пластик и одно в Беларусь. В очередь НЕ ставятся,
текст — на экран и в _ops/test-pisma-meyer.json. Компании без письма Meyer,
с вердиктом «мейер»/«оба», самый подробный паспорт."""
import io
import json
import os
import re
import sqlite3
import sys

os.environ.setdefault("PROVIDER_THINKING_FIELD", "omit")
sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
import gen_provider  # noqa: E402
from sender.ai_letter import AiLetterGen, load_facts  # noqa: E402
from sender.ai_quota import build_ai_quota  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402

ОТРАСЛИ = [("кондитерка", r"кондит|шоколад|конфет|печень|вафл", "Россия 9000"),
           ("мясо", r"мяс|колбас|птиц|полуфабрик", "Россия 9000"),
           ("зерно", r"зерн|элеват|мук|круп", "Россия 9000"),
           ("пластик", r"пласт|полимер|гранул|ПЭТ", "Россия 9000"),
           ("Беларусь", r".", "Белорусь 1000")]
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
верд = {str(r[0]): r[1] for r in e.execute("SELECT inn, verdikt_napr FROM companies")}
с_письмом = {str(r[0]) for r in c.execute(
    "SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status IN "
    "('pending_review','approved','scheduled','sending','sent')")}


def caller(prompt, *a, **k):
    системный, тело = gen_provider.razrezat_promt(prompt)
    m = gen_provider._raw_stream([{"role": "user", "content": тело}], "claude-sonnet-4-6", 6000,
                                 thinking=False, effort="low", system=системный)
    return "".join(b.text for b in m.content if getattr(b, "type", "") == "text")


итог, были = [], set()
for метка, rx, гр in ОТРАСЛИ:
    канд = []
    for rid, inn, сег in c.execute("SELECT id, inn, segment FROM recipients WHERE extra_json LIKE ?", ("%" + гр + "%",)):
        inn = str(inn)
        if inn in были or inn in с_письмом or верд.get(inn) not in ("мейер", "оба"):
            continue
        d = q._site_facts(inn) or {}
        текст = " ".join(str(v) for v in d.values()) + " " + str(сег or "")
        if not re.search(rx, текст, re.I):
            continue
        канд.append((sum(1 for k in ("продукция", "сырьё", "оборудование_линии", "масштаб") if d.get(k)), rid, inn))
        if len(канд) > 60:
            break
    if not канд:
        print("\n=== %s: кандидата нет" % метка)
        continue
    канд.sort(reverse=True)
    for _п, rid, inn in канд[:3]:
        rec = store.get_recipient(rid)
        req = q._request(rec)
        req["target_division"] = "meyer"
        try:
            q._add_ideas_generic([req])
        except Exception:  # noqa: BLE001
            pass
        try:
            res = AiLetterGen(caller, facts_by_division={"meyer": load_facts(division="meyer")}, best_of=1,
                              checker=caller).generate([req])
        except Exception as ex:  # noqa: BLE001
            print("\n=== %s | %s | сбой: %s" % (метка, rec.company_name, str(ex)[:90]))
            continue
        L = res.ok.get(0)
        черн = res.drafts.get(0) if hasattr(res, "drafts") else None
        print("\n=== %s | %s | %s" % (метка, rec.company_name, rec.email))
        print("ГОДНО" if L else "БРАК: %s" % res.rejected.get(0))
        print("Тема: %s\n\n%s" % ((L or черн or {}).get("subject"), (L or черн or {}).get("body")))
        итог.append({"отрасль": метка, "компания": rec.company_name, "ok": bool(L),
                     "тема": (L or черн or {}).get("subject"), "тело": (L or черн or {}).get("body"),
                     "брак": res.rejected.get(0)})
        были.add(inn)
        if L:
            break
json.dump(итог, io.open(r"C:\sender\_ops\test-pisma-meyer.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("=== ТЕСТ ПИСЕМ MEYER ===")
