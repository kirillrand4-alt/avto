# -*- coding: utf-8 -*-
"""Видит ли БОЕВАЯ линза паспорт сайта. И отдача прогона по возрасту карточки.

Утром я собрал карточку получателя из recipients.extra_json и получил
«сомнительно» — но боевой путь собирает её через AiQuota._request, а тот
подтягивает паспорт из enrich.db/site_facts (ai_quota.py:1147). Значит мой
утренний вывод про «линза не видит паспорт» мог быть про мою реконструкцию,
а не про конвейер. Проверяем тем же вызовом, каким ходит бой.
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import teh_lens_prompt, _parse_json     # noqa: E402
from sender.ai_quota import build_ai_quota                    # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402
from sender.review_lenses import default_caller               # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(r"C:\sender\sender.db")
q = build_ai_quota(store, cfg)

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
c.row_factory = sqlite3.Row
items = []
for об in (12173, 12174):
    r = c.execute("SELECT recipient_id, subject, body, edited_subject,"
                  "       edited_body FROM confirm_reviews WHERE id=?",
                  (об,)).fetchone()
    rec = store.get_recipient(r["recipient_id"])
    зап = q._request(rec)
    пасп = (зап.get("extra") or {}).get("site_facts") or {}
    куски = []
    for к in ("продукция", "сырьё", "мощности", "упаковка_фасовка", "расширение"):
        v = пасп.get(к) if isinstance(пасп, dict) else None
        if isinstance(v, str):
            v = [v]
        if v:
            куски.append("%s: %s" % (к, "; ".join(str(x) for x in v[:8])))
    print("review %d: паспорт в боевом запросе — %s (%d полей)"
          % (об, "ЕСТЬ" if пасп else "нет", len(пасп) if пасп else 0))
    items.append((об, str(зап.get("company_name") or ""),
                  str(зап.get("activity") or ""), str(зап.get("okved") or ""),
                  (r["edited_subject"] or "").strip() or r["subject"],
                  (r["edited_body"] or "").strip() or r["body"],
                  " | ".join(куски)[:700]))

текст, _м = default_caller(teh_lens_prompt(items, "три", "kc"),
                           max_tokens=8000, model="claude-sonnet-4-6")
данные = _parse_json(текст, "teh3-boy")
print("\n=== ЛИНЗА БОЕВЫМ ПУТЁМ ===")
for vd in данные.get("verdicts", []):
    print("   review %s: %-12s %s"
          % (vd.get("idx"), vd.get("verdict"), str(vd.get("chto_ne_tak") or "")[:110]))

# --- отдача прогона по возрасту карточки ------------------------------------
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
свежие = set()
for r in c.execute("SELECT inn, substr(created_at,1,10) д FROM recipients"
                   " WHERE inn IS NOT NULL"
                   "   AND COALESCE(extra_json,'') LIKE '%Партия 935%'"):
    if r["д"] >= "2026-08-31":
        свежие.add(str(r["inn"] or ""))
c.close()

сч = defaultdict(Counter)
брак_причины = Counter()
with io.open(ЖУРНАЛ, encoding="utf-8") as f:
    строки = f.readlines()
for с in строки[-6000:]:
    try:
        z = json.loads(с)
    except Exception:                                         # noqa: BLE001
        continue
    if z.get("этап") != "итог" or z.get("день") != "2026-08-31":
        continue
    if str(z.get("направление") or "") != "meyer":
        continue
    г = "карточка от 31.08" if str(z.get("inn") or "") in свежие else "карточка старше"
    сч[г]["ок" if z.get("ок") else "брак"] += 1
    if not z.get("ок"):
        б = z.get("брак")
        брак_причины[str(б)[:70]] += 1

print("\n=== ОТДАЧА СЕГОДНЯШНЕГО ПРОГОНА MEYER ===")
для_всех = Counter()
for г in sorted(сч):
    всего = sum(сч[г].values())
    для_всех.update(сч[г])
    print("   %-20s всего %4d, ок %4d (%.0f%%), брак %4d"
          % (г, всего, сч[г]["ок"], 100.0 * сч[г]["ок"] / всего, сч[г]["брак"]))
в = sum(для_всех.values())
if в:
    print("   ИТОГО               всего %4d, ок %4d (%.0f%%), брак %4d"
          % (в, для_всех["ок"], 100.0 * для_всех["ок"] / в, для_всех["брак"]))
if брак_причины:
    print("\n   причины брака:")
    for п, n in брак_причины.most_common(6):
        print("      %-70s %3d" % (п, n))

print("\n=== ИТОГ ===")
print("паспорт в карточке recipients.extra_json: нет ни у кого (0 из 45067)")
print("паспорт в боевом запросе _request: подтягивается из enrich.db отдельно")
