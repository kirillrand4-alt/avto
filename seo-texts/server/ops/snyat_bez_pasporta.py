# -*- coding: utf-8 -*-
"""Снять из очереди карточки второго адреса, где домен почты не подтверждён
паспортом сайта либо паспорта нет вовсе (владелец 27.08: «68 убери»).

Без --katit только считает. Снятые пишем в _ops\\vtorye-snyatye.jsonl с fsync.
"""
import io
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
СЛЕД = r"C:\sender\_ops\vtorye-snyatye.jsonl"

карточки = []
for с in io.open(r"C:\sender\_ops\vtorye-adresa.jsonl", encoding="utf-8"):
    d = json.loads(с)
    карточки.append((str(d["inn"]), d["email"].lower(), int(d["review"])))
инны = sorted({и for и, _, _ in карточки})
print("карточек в партии: %d, режим: %s"
      % (len(карточки), "БОЕВОЙ" if КАТИТЬ else "вхолостую"))


def дом(u):
    u = str(u or "").strip().lower()
    м = re.search(r"//([^/]+)", u)
    d = м.group(1) if м else u.split("/")[0]
    d = d[4:] if d.startswith("www.") else d
    return d if "." in d else ""


e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=90)
e.row_factory = sqlite3.Row
паспорт, откуда = {}, {}
for i in range(0, len(инны), 400):
    к = инны[i:i + 400]; зн = ",".join("?" * len(к))
    for r in e.execute("SELECT inn, site, sources_json FROM site_facts "
                       " WHERE inn IN (%s) AND COALESCE(facts_json,'')<>''" % зн, к):
        for д in [дом(r["site"])] + [дом(u) for u in re.findall(
                r"https?://[^\s\"']+", str(r["sources_json"] or ""))[:20]]:
            if д:
                паспорт.setdefault(str(r["inn"]), set()).add(д)
    for r in e.execute("SELECT inn, email, source_url FROM emails "
                       " WHERE inn IN (%s)" % зн, к):
        откуда[(str(r["inn"]), (r["email"] or "").lower())] = дом(r["source_url"])
e.close()

снимать = []
сч = Counter()
for инн, адрес, rev in карточки:
    пас = паспорт.get(инн) or set()
    д_почты = адрес.split("@", 1)[1]
    д_ист = откуда.get((инн, адрес), "")
    if not пас:
        снимать.append((rev, инн, адрес, "паспорта сайта нет"))
        сч["паспорта сайта нет"] += 1
    elif not (д_почты in пас or (д_ист and (д_ист in пас or д_ист == д_почты))):
        снимать.append((rev, инн, адрес, "домен почты не подтверждён паспортом"))
        сч["домен почты не из паспорта"] += 1
    else:
        сч["остаётся"] += 1
print("")
for к, n in сч.most_common():
    print("   %-34s %5d" % (к, n))
print("к снятию: %d" % len(снимать))
for rev, и, а, п in снимать[:6]:
    print("   rev %-6s %-13s %-30s %s" % (rev, и, а[:30], п))

if not КАТИТЬ:
    raise SystemExit(0)

from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.wiring import build_deps                              # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = build_deps(cfg, store, dry_run=True).confirm

уже = set()
if os.path.exists(СЛЕД):
    for с in io.open(СЛЕД, encoding="utf-8", errors="replace"):
        try:
            уже.add(int(json.loads(с)["review"]))
        except Exception:                                          # noqa: BLE001
            pass
итог = Counter()
поток = io.open(СЛЕД, "a", encoding="utf-8")
for rev, инн, адрес, причина in снимать:
    if rev in уже:
        итог["уже снято"] += 1
        continue
    try:
        ок = cs.skip(rev, reason="второй адрес: " + причина,
                     operator="проверка паспорта 27.08")
        итог["снято" if ок else "не в pending (пропуск)"] += 1
        if ок:
            поток.write(json.dumps(
                {"review": rev, "inn": инн, "email": адрес, "prichina": причина,
                 "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False) + "\n")
            поток.flush(); os.fsync(поток.fileno())
    except Exception as ex:                                        # noqa: BLE001
        итог["ошибка: " + str(ex)[:44]] += 1
поток.close()
print("")
print("=== итог снятия ===")
for к, n in итог.most_common():
    print("   %-40s %5d" % (к, n))
