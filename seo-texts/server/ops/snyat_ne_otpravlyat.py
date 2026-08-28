# -*- coding: utf-8 -*-
"""Снять из очереди письма с вердиктом судьи «не отправлять».

Владелец 28.08: «снимай которые не отправлять».

Придержим один класс ложных срабатываний: судья считал выдумкой счётчики
наших опубликованных проектов («46 опубликованных проектов по Новосибирской
области»). Цифра настоящая, из индекса проектов, — судья её видеть не мог,
в карточке компании её нет. Такие письма не снимаем, а показываем отдельно.

Без --katit только считает. Снятые пишем в _ops\\vtorye-snyatye.jsonl с fsync.
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
СЛЕД = r"C:\sender\_ops\vtorye-snyatye.jsonl"

вердикты = {}
for с in io.open(r"C:\sender\_ops\sud-vtoryh.jsonl", encoding="utf-8"):
    try:
        d = json.loads(с)
        вердикты[int(d["id"])] = d
    except Exception:                                            # noqa: BLE001
        continue
print("вердиктов судьи: %d" % len(вердикты))
print("раскладка: %s" % dict(Counter(str(v.get("verdikt")) for v in вердикты.values())))

нельзя = [v for v in вердикты.values() if str(v.get("verdikt")) == "не отправлять"]


def tolko_schyotchik(v):
    """Вердикт держится только на счётчике наших проектов — ложная тревога."""
    вы = str(v.get("vydumka") or "").lower()
    нт = str(v.get("chto_ne_tak") or "").lower()
    про_счёт = ("опубликован" in вы or "опубликован" in нт
                or "проектов" in вы or "кейс" in вы)
    return про_счёт and v.get("napravlenie_verno") is True and not (
        "не имеет отно" in нт or "не нужн" in нт or "не треб" in нт)


придержать = [v for v in нельзя if tolko_schyotchik(v)]
снимать = [v for v in нельзя if not tolko_schyotchik(v)]
print("")
print("«не отправлять»: %d, из них придержано как ложная тревога: %d, к снятию: %d"
      % (len(нельзя), len(придержать), len(снимать)))
for v in придержать[:5]:
    print("   придержал rev %-6s %s" % (v["id"], str(v.get("chto_ne_tak"))[:82]))

# только те, что ещё в очереди
s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
ids = [int(v["id"]) for v in снимать] or [0]
зн = ",".join("?" * len(ids))
живые = {}
for r in s.execute("SELECT cr.id, cr.email, cr.inn, r.company_name "
                   "  FROM confirm_reviews cr LEFT JOIN recipients r "
                   "    ON r.id=cr.recipient_id "
                   " WHERE cr.id IN (%s) AND cr.status='pending'" % зн, ids):
    живые[int(r[0])] = (r[1], str(r[2] or ""), str(r[3] or "")[:40])
s.close()
print("из них ещё в очереди: %d" % len(живые))
for i, (rev, (по, инн, имя)) in enumerate(sorted(живые.items())):
    if i >= 6:
        break
    v = вердикты[rev]
    print("   rev %-6s %-26s %-30s %s"
          % (rev, str(по)[:26], имя[:30], str(v.get("chto_ne_tak"))[:44]))
if not КАТИТЬ or not живые:
    raise SystemExit(0)

from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.wiring import build_deps                              # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = build_deps(cfg, store, dry_run=True).confirm
итог = Counter()
поток = io.open(СЛЕД, "a", encoding="utf-8")
for rev, (по, инн, имя) in живые.items():
    v = вердикты[rev]
    почему = str(v.get("chto_ne_tak") or "судья: не отправлять")[:170]
    try:
        ок = cs.skip(rev, reason="судья писем: " + почему,
                     operator="судья писем 28.08")
        итог["снято" if ок else "не в pending"] += 1
        if ок:
            поток.write(json.dumps(
                {"review": rev, "inn": инн, "email": по,
                 "prichina": "судья: " + почему,
                 "napravlenie": v.get("napravlenie_pochemu"),
                 "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False) + "\n")
            поток.flush()
            os.fsync(поток.fileno())
    except Exception as ex:                                       # noqa: BLE001
        итог["ошибка: " + str(ex)[:44]] += 1
поток.close()
print("")
print("=== итог ===")
for к, n in итог.most_common():
    print("   %-34s %5d" % (к, n))
