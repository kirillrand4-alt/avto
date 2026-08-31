# -*- coding: utf-8 -*-
"""Прогнать письма из очереди по боевым проверкам генерации.

Что именно гоняем — ровно то, что стоит на пути обычного письма:
  1) ai_letter.gate(...) — механический гейт (стоп-лексика, тема, объём,
     финал, марки, служебный текст, перекрёстная лексика направления);
  2) три линзы одним вызовом — teh_lens_prompt(items,'три',направление),
     через провайдерский шлюз моделью проверок (ai_quota.checker_model),
     партиями по три письма, как в _teh_lens_verdicts.

Вердикты пишем в серверный jsonl, а не только в вывод.
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, r"C:\sender")   # только корень: C:\sender\sender\sender.py
                                   # затенил бы пакет sender
import sqlite3                                                # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\progon-agentskih-pisem.jsonl"
ИДЫ = [int(а) for а in sys.argv[1:] if а.isdigit()] or list(range(12169, 12179))
МОДЕЛЬ = "claude-sonnet-4-6"

from sender import ai_letter as AL                            # noqa: E402
from sender.review_lenses import default_caller               # noqa: E402

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
s.row_factory = sqlite3.Row
письма = {}
for r in s.execute("SELECT id, campaign_id, recipient_id, inn, email, subject,"
                   "       body, edited_subject, edited_body, status"
                   "  FROM confirm_reviews WHERE id IN (%s)"
                   % ",".join("?" * len(ИДЫ)), ИДЫ):
    тема = (r["edited_subject"] or "").strip() or (r["subject"] or "")
    тело = (r["edited_body"] or "").strip() or (r["body"] or "")
    письма[r["id"]] = {"review": r["id"], "camp": r["campaign_id"],
                       "rid": r["recipient_id"], "inn": r["inn"],
                       "email": r["email"], "subject": тема, "body": тело,
                       "status": r["status"]}
получатели = {}
for кл, п in письма.items():
    q = s.execute("SELECT company_name, okved, contact_name, extra_json, inn"
                  "  FROM recipients WHERE id=?", (п["rid"],)).fetchone()
    доп = {}
    if q and q["extra_json"]:
        try:
            доп = json.loads(q["extra_json"]) or {}
        except Exception:                                     # noqa: BLE001
            доп = {}
    получатели[кл] = {
        "company_name": (q["company_name"] if q else "") or "",
        "okved": (q["okved"] if q else "") or "",
        "contact_name": (q["contact_name"] if q else "") or "",
        "activity": str(доп.get("activity") or ""),
        "extra": доп,
    }
s.close()
print("писем взято: %d из %d запрошенных" % (len(письма), len(ИДЫ)))

# --- направление и режим -----------------------------------------------------
for кл, п in письма.items():
    r = dict(получатели[кл])
    доп = r["extra"]
    r["mode"] = "NEWS" if (доп.get("news_object") and доп.get("city")) else "GENERIC"
    напр, почему = AL.target_division(r, default="kc")
    п["division"], п["div_why"], п["mode"] = напр, почему, r["mode"]

# --- 1) механический гейт ----------------------------------------------------
print("\n=== ГЕЙТ ===")
for кл in sorted(письма):
    п = письма[кл]
    r = получатели[кл]
    брак = AL.gate(п["subject"], п["body"], mode=п["mode"], extra=r,
                   facts=AL.load_facts(division=п["division"]),
                   division=п["division"])
    п["gate"] = list(брак)
    слов = len(п["body"].split())
    print("  %d %-26s %-6s %-8s %3d слов  %s"
          % (кл, (r["company_name"] or "")[:26], п["division"], п["mode"], слов,
             "ЧИСТО" if not брак else "; ".join(брак)[:110]))

# --- 2) три линзы через провайдера -------------------------------------------
def чек(prompt):
    текст, _м = default_caller(prompt, max_tokens=8000, model=МОДЕЛЬ)
    return текст

по_напр = {}
for кл in sorted(письма):
    по_напр.setdefault(письма[кл]["division"], []).append(кл)

вызовов, т0 = 0, time.time()
for напр, свои in по_напр.items():
    for n in range(0, len(свои), 3):
        часть = свои[n:n + 3]
        items = []
        for кл in часть:
            r = получатели[кл]
            пасп = (r["extra"].get("site_facts") or {})
            куски = []
            for к in ("продукция", "сырьё", "мощности", "упаковка_фасовка",
                      "расширение"):
                v = пасп.get(к) if isinstance(пасп, dict) else None
                if isinstance(v, str):
                    v = [v]
                if v:
                    куски.append("%s: %s" % (к, "; ".join(str(x) for x in v[:8])))
            items.append((кл, r["company_name"], r["activity"], r["okved"],
                          письма[кл]["subject"], письма[кл]["body"],
                          " | ".join(куски)[:700]))
        промпт = AL.teh_lens_prompt(items, "три", напр)
        try:
            сырое = чек(промпт)
            вызовов += 1
            данные = AL._parse_json(сырое, "teh3-%s-%d" % (напр, n))
        except Exception as e:                                # noqa: BLE001
            print("  линза упала на партии %s/%d: %s" % (напр, n, e))
            continue
        for vd in данные.get("verdicts", []):
            try:
                vi = int(vd["idx"])
            except (KeyError, TypeError, ValueError):
                continue
            if vi in письма:
                письма[vi]["lens"] = str(vd.get("verdict") or "").strip().lower()
                письма[vi]["lens_why"] = str(vd.get("chto_ne_tak") or "")[:220]
                письма[vi]["lens_drugoe"] = str(vd.get("drugoe") or "").strip()

with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
    for кл in sorted(письма):
        п = dict(письма[кл])
        п["ts"] = int(time.time())
        п["company"] = получатели[кл]["company_name"]
        п.pop("body", None)
        f.write(json.dumps(п, ensure_ascii=False) + "\n")
    f.flush()
    os.fsync(f.fileno())

print("\n=== ТРИ ЛИНЗЫ (вызовов %d, %.0f с) ===" % (вызовов, time.time() - т0))
for кл in sorted(письма):
    п = письма[кл]
    print("  %d %-26s %-11s %s"
          % (кл, (получатели[кл]["company_name"] or "")[:26],
             п.get("lens", "нет ответа"),
             (п.get("lens_why") or "")[:100]
             + ("  → переставить в %s" % п["lens_drugoe"]
                if п.get("lens_drugoe") else "")))

чисто = [к for к in письма if not письма[к]["gate"]
         and письма[к].get("lens") == "верно"]
сомн = [к for к in письма if письма[к].get("lens") == "сомнительно"]
ошиб = [к for к in письма if письма[к].get("lens") == "ошибка"]
сгейтом = [к for к in письма if письма[к]["gate"]]
print("\n=== ИТОГ ===")
print("писем прогнано: %d" % len(письма))
print("прошли обе проверки чисто:      %d  %s" % (len(чисто), sorted(чисто)))
print("зацепил механический гейт:      %d  %s" % (len(сгейтом), sorted(сгейтом)))
print("линза: сомнительно              %d  %s" % (len(сомн), sorted(сомн)))
print("линза: ошибка                   %d  %s" % (len(ошиб), sorted(ошиб)))
print("вердикты записаны в %s" % ЖУРНАЛ)
