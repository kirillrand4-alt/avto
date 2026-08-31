# -*- coding: utf-8 -*-
"""Подложить работнику VPS адреса живой очереди, которых он не проверял.

Механика (VPS-PROVERKI-ADRESOV.md): на дропе лежит файл-задание
`probe-zadanie.json` — список адресов. Раннер на проверочном VPS смотрит
задания каждые 20 секунд, гоняет SMTP-пробу со своего IP и кладёт вердикты
в `probe-rezultat.jsonl`; панель забирает их через ProbeSync.забрать().

Отбираем ВСЮ живую очередь (pending + approved + edited), а не только то, что
уже в расписании: сегодняшняя партия стоит в pending, и соседний
otdat_rabotniku_neprovennye.py её не видит.

Не проверял = в addr_probe нет строки ЛИБО у неё source не 'проба'.
Задание ДОПИСЫВАЕТСЯ, чужие ждущие адреса не выбиваем.

    python otdat_partiyu_rabotniku.py              посчитать
    python otdat_partiyu_rabotniku.py --otpravit   отдать
"""
import json
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.addr_probe import build_addr_probe                # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.probe_sync import build_probe_sync, ЗАДАНИЕ       # noqa: E402
from sender.store import Store                                # noqa: E402

ОТПРАВИТЬ = "--otpravit" in sys.argv
ПРЕДЕЛ = int(next((a for a in sys.argv[1:] if a.isdigit()), "0"))

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
проба = build_addr_probe(store, cfg)
цикл = build_probe_sync(store, getattr(проба, "probe_", проба), cfg)
print("ProbeSync включён: %s; addr_probe (панельная SMTP-проба): %s"
      % (цикл.enabled(), проба.enabled()))

with store._lock:
    ряды = store._conn.execute(
        "SELECT lower(trim(cr.email)) e, COALESCE(p.source,'') src,"
        "       COALESCE(p.verdict,'') v, cr.campaign_id c, cr.status st,"
        "       cr.created_at ct"
        "  FROM confirm_reviews cr"
        "  LEFT JOIN addr_probe p ON p.email = lower(trim(cr.email))"
        " WHERE cr.status IN ('pending','approved','edited')"
        "   AND COALESCE(cr.kind,'outbound') <> 'reply'"
        "   AND cr.email LIKE '%@%'").fetchall()

счёт = Counter()
надо, свежие_партии = [], []
сегодня = time.strftime("%Y-%m-%d")
for r in ряды:
    e = str(r["e"] or "").strip()
    if not e:
        continue
    if str(r["src"]) == "проба":
        счёт["работник уже проверял"] += 1
        continue
    счёт["работник не видел (вердикт «%s»)" % (r["v"] or "нет")] += 1
    if r["c"] == 11 and str(r["ct"] or "").startswith(сегодня):
        свежие_партии.append(e)
    else:
        надо.append(e)

# Сегодняшняя партия идёт ПЕРВОЙ: её письма ближе всех к одобрению.
порядок, видели = [], set()
for а in свежие_партии + надо:
    if а not in видели:
        видели.add(а)
        порядок.append(а)
if ПРЕДЕЛ:
    порядок = порядок[:ПРЕДЕЛ]

print("\nписем в живой очереди: %d" % len(ряды))
for к, n in счёт.most_common(8):
    print("   %5d  %s" % (n, к))
print("\nадресов к отправке работнику: %d (из них сегодняшняя партия Meyer: %d)"
      % (len(порядок), len(set(свежие_партии) & set(порядок))))

было = []
try:
    сыро = цикл._дроп("GET", ЗАДАНИЕ).decode("utf-8", "replace")
    было = json.loads(сыро)
    if isinstance(было, dict):
        было = было.get("emails") or []
except Exception as ex:                                       # noqa: BLE001
    print("задания на дропе ещё нет: %s" % str(ex)[:80])
print("сейчас в задании на дропе: %d адресов" % len(было or []))

if not ОТПРАВИТЬ:
    print("\n[сухой прогон] отдать — с ключом --otpravit")
    raise SystemExit(0)

список, видели2 = [], set()
for а in порядок + [str(x).strip().lower() for x in (было or [])]:
    if а and а not in видели2:
        видели2.add(а)
        список.append(а)
цикл._дроп("PUT", ЗАДАНИЕ,
           json.dumps(список, ensure_ascii=False).encode("utf-8"))
разбужен = False
try:
    цикл._толкнуть(len(список))
    разбужен = True
except Exception as e:                                        # noqa: BLE001
    print("растолкать работника не вышло: %s" % str(e)[:120])

print("\n=== ИТОГ ===")
print("в задании на дропе теперь: %d адресов (было %d, добавил %d)"
      % (len(список), len(было or []), len(порядок)))
print("работник разбужен толчком: %s" % ("да" if разбужен else
                                         "нет — уйдёт обычным кругом"))
print("вердикты приедут в addr_probe через ProbeSync.забрать()")
