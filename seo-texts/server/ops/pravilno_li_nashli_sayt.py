# -*- coding: utf-8 -*-
"""Тот ли сайт привязан к выбывшим компаниям."""
import io
import json
import re
import sqlite3
from collections import Counter


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


def домен(з):
    з = str(з or "").strip().lower()
    з = re.sub(r"^[a-z]+://", "", з).split("/")[0].split("?")[0].strip(".")
    return з[4:] if з.startswith("www.") else (з if "." in з else "")


ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
попыток, готово = Counter(), set()
итогов = Counter()
with io.open(ЖУРНАЛ, encoding="utf-8") as f:
    for с in f.readlines():
        try:
            z = json.loads(с)
        except Exception:                                     # noqa: BLE001
            continue
        и = цифры(z.get("inn"))
        if not и:
            continue
        э = str(z.get("этап") or "")
        if э == "отмена_попытки":
            попыток[и] = max(0, попыток[и] - 1)
            continue
        if z.get("ок") or z.get("тело"):
            готово.add(и)
        if э != "итог":
            попыток[и] += 1
        if э == "итог":
            итогов[и] += 1
отсеянные = [и for и in попыток
             if попыток[и] >= 3 and и not in готово and not итогов[и]]
print("компаний, отсеянных предклассификатором: %d" % len(отсеянные))

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
e.row_factory = sqlite3.Row
таблицы = [r[0] for r in e.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")]
for т in ("qc_site", "raznoglasie_sait"):
    if т in таблицы:
        столбцы = [x[1] for x in e.execute("PRAGMA table_info(%s)" % т)]
        n = e.execute("SELECT COUNT(*) FROM %s" % т).fetchone()[0]
        print("   %-18s строк %6d, колонки: %s" % (т, n, ", ".join(столбцы[:10])))

карт = {}
for i in range(0, len(отсеянные), 400):
    ч = отсеянные[i:i + 400]
    for r in e.execute("SELECT inn, name, site, site_source, verified,"
                       "       verified_url, okved FROM companies"
                       " WHERE inn IN (%s)" % ",".join("?" * len(ч)), ч):
        карт[цифры(r["inn"])] = dict(r)
почты = {}
for i in range(0, len(отсеянные), 400):
    ч = отсеянные[i:i + 400]
    for r in e.execute("SELECT inn, email FROM emails WHERE inn IN (%s)"
                       % ",".join("?" * len(ч)), ч):
        почты.setdefault(цифры(r["inn"]), set()).add(
            str(r["email"] or "").split("@")[-1].lower())
e.close()

источники = Counter()
совпал, не_совпал, нет_данных = 0, 0, 0
примеры_расхождений = []
for и in отсеянные:
    к = карт.get(и)
    if not к:
        нет_данных += 1
        continue
    источники[str(к.get("site_source") or "(пусто)")] += 1
    д = домен(к.get("site"))
    дп = почты.get(и) or set()
    if not д or not дп:
        нет_данных += 1
    elif д in дп:
        совпал += 1
    else:
        не_совпал += 1
        if len(примеры_расхождений) < 12:
            примеры_расхождений.append(
                (к.get("name"), к.get("okved"), д, sorted(дп)[:2],
                 к.get("site_source")))

print("\n=== ОТКУДА ВЗЯЛСЯ САЙТ ===")
for и_, n in источники.most_common(8):
    print("   %-22s %5d" % (и_, n))
print("\n=== ДОМЕН ПОЧТЫ ПРОТИВ ДОМЕНА САЙТА ===")
print("   совпал (сайт почти наверняка их):     %5d" % совпал)
print("   НЕ совпал (сайт мог быть чужой):      %5d" % не_совпал)
print("   сравнить не с чем:                    %5d" % нет_данных)
print("\n=== ПРИМЕРЫ РАСХОЖДЕНИЙ ===")
for имя, окв, д, дп, ист in примеры_расхождений:
    print("   %-30s ОКВЭД %-8s сайт %-22s почта %s  [%s]"
          % (str(имя)[:30], str(окв)[:8], д, ",".join(дп), ист))
