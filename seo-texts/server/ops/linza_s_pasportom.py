# -*- coding: utf-8 -*-
"""Гипотеза: линза сомневается не в письме, а в пустоте карточки.

Паспорт сайта живёт в enrich.db site_facts, но в карточку получателя
(recipients.extra_json) он не переехал — линза судит по одному ОКВЭДу. Ровно
тот отказ, про который предупреждает комментарий в teh_lens_prompt.

Считаем, у скольких из десяти паспорт есть в карточке и есть ли он в
обогащении, и перепрогоняем линзу, подставив паспорт из обогащения.
"""
import io
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
ИДЫ = list(range(12169, 12179))
МОДЕЛЬ = "claude-sonnet-4-6"
ЖУРНАЛ = r"C:\sender\_ops\progon-agentskih-pisem.jsonl"

from sender import ai_letter as AL                            # noqa: E402
from sender.review_lenses import default_caller               # noqa: E402

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
s.row_factory = sqlite3.Row
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=60)
e.row_factory = sqlite3.Row

карточки = {}
for об in ИДЫ:
    r = s.execute("SELECT c.id, c.subject, c.body, c.edited_subject, "
                  "       c.edited_body, r.company_name, r.okved, r.inn, "
                  "       r.extra_json FROM confirm_reviews c "
                  "  JOIN recipients r ON r.id=c.recipient_id WHERE c.id=?",
                  (об,)).fetchone()
    if not r:
        continue
    доп = {}
    try:
        доп = json.loads(r["extra_json"] or "{}") or {}
    except Exception:                                         # noqa: BLE001
        pass
    ф = e.execute("SELECT facts_json FROM site_facts WHERE inn=?",
                  (r["inn"],)).fetchone()
    из_обогащения = {}
    if ф and ф["facts_json"]:
        try:
            из_обогащения = json.loads(ф["facts_json"]) or {}
        except Exception:                                     # noqa: BLE001
            pass
    карточки[об] = {
        "name": r["company_name"] or "", "okved": r["okved"] or "",
        "inn": r["inn"], "activity": str(доп.get("activity") or ""),
        "subject": (r["edited_subject"] or "").strip() or r["subject"] or "",
        "body": (r["edited_body"] or "").strip() or r["body"] or "",
        "пасп_карточка": доп.get("site_facts") or {},
        "пасп_обогащение": из_обогащения,
    }
s.close()
e.close()

print("=== ПАСПОРТ САЙТА: В КАРТОЧКЕ ПРОТИВ ОБОГАЩЕНИЯ ===")
нет_в_карточке = []
for об in sorted(карточки):
    к = карточки[об]
    вк = bool(к["пасп_карточка"])
    во = bool(к["пасп_обогащение"])
    if not вк:
        нет_в_карточке.append(об)
    print("  %d %-26s карточка:%-4s обогащение:%-4s activity:%s"
          % (об, к["name"][:26], "есть" if вк else "НЕТ",
             "есть" if во else "нет", "есть" if к["activity"] else "нет"))


def куски(пасп):
    вых = []
    for кл in ("продукция", "сырьё", "мощности", "упаковка_фасовка",
               "расширение"):
        v = пасп.get(кл) if isinstance(пасп, dict) else None
        if isinstance(v, str):
            v = [v]
        if v:
            вых.append("%s: %s" % (кл, "; ".join(str(x) for x in v[:8])))
    return " | ".join(вых)[:700]


def прогнать(об_список, с_паспортом):
    items = []
    for об in об_список:
        к = карточки[об]
        пасп = к["пасп_обогащение"] if с_паспортом else к["пасп_карточка"]
        items.append((об, к["name"], к["activity"], к["okved"],
                      к["subject"], к["body"], куски(пасп)))
    промпт = AL.teh_lens_prompt(items, "три", "kc")
    текст, _м = default_caller(промпт, max_tokens=8000, model=МОДЕЛЬ)
    данные = AL._parse_json(текст, "teh3-pasport")
    вых = {}
    for vd in данные.get("verdicts", []):
        try:
            vi = int(vd["idx"])
        except (KeyError, TypeError, ValueError):
            continue
        вых[vi] = (str(vd.get("verdict") or "").strip().lower(),
                   str(vd.get("chto_ne_tak") or "")[:200])
    return вых


спорные = [12173, 12174]
т0 = time.time()
без = прогнать(спорные, с_паспортом=False)
с_ = прогнать(спорные, с_паспортом=True)

with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
    for об in спорные:
        f.write(json.dumps({"ts": int(time.time()), "review": об,
                            "opyt": "pasport",
                            "bez_pasporta": без.get(об),
                            "s_pasportom": с_.get(об)},
                           ensure_ascii=False) + "\n")
    f.flush()
    os.fsync(f.fileno())

print("\n=== ТА ЖЕ ЛИНЗА, ТО ЖЕ ПИСЬМО, РАЗНЫЕ ДАННЫЕ (%.0f с) ==="
      % (time.time() - т0))
for об in спорные:
    к = карточки[об]
    print("\n  %d %s" % (об, к["name"]))
    print("     как сейчас (без паспорта): %-12s %s"
          % (без.get(об, ("нет ответа", ""))[0], без.get(об, ("", ""))[1][:110]))
    print("     с паспортом из обогащения: %-12s %s"
          % (с_.get(об, ("нет ответа", ""))[0], с_.get(об, ("", ""))[1][:110]))
    print("     паспорт: %s" % куски(к["пасп_обогащение"])[:200])

print("\n=== ИТОГ ===")
print("паспорта сайта нет в карточке ни у одного из %d писем: %s"
      % (len(нет_в_карточке), нет_в_карточке == sorted(карточки)))
print("у скольких паспорт лежит в обогащении и просто не доехал: %d"
      % sum(1 for к in карточки.values() if к["пасп_обогащение"]))
print("вердикты записаны в %s" % ЖУРНАЛ)
