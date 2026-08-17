# -*- coding: utf-8 -*-
"""Доспросить снятых «неясных» работником и вернуть тех, кто ожил.

Порядок действий 17.08 сыграл против нас: сначала сняли 777 компаний с
неподтверждённым адресом из партии, а потом запустили переспрос - и он
вернулся пустым, потому что ищет адреса ПО ГРУППЕ, а их там больше нет.

Здесь список берётся из журнала снятия, а не из группы. Спрашиваем только
тех, чей вердикт означает «узнать не удалось» - «неясно» и «отказ пробе».
«Нет ящика» и «нет MX» окончательны, их не тревожим.

У работника на VPS есть обратная запись DNS, у основного сервера нет:
корпоративные почтовики рвут сессию именно с безымянным адресом, отсюда и
«неясно». Поэтому доспрашивает он.

Ожил - значит вердикт стал «есть» или «принимает всё». Такую компанию
возвращаем в партию ровно в те группы, из которых сняли (журнал их хранит),
и пишем строку о возврате.

argv: [лимит_секунд=1500]
"""
import io
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                               # noqa: E402
from sender.probe_sync import build_probe_sync                 # noqa: E402
from sender.addr_probe import build_addr_probe                 # noqa: E402
from sender.store import Store                                 # noqa: E402

ГРУППА = "Партия 935"
ЖУРНАЛ = r"C:\sender\_ops\partiya-snyatye-nezhivye.jsonl"
ВОЗВРАТЫ = r"C:\sender\_ops\partiya-vozvrashchennye.jsonl"
СПРАШИВАЕМ = ("неясно", "отказ пробе")
ЖИВЫЕ = ("есть", "принимает всё")
ПОРЦИЯ = 100
ПАУЗА = 45
СТАРТ = time.time()
ЛИМИТ_СЕК = (int(sys.argv[1]) if len(sys.argv) > 1 else 1500) - 120

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
probe = build_addr_probe(store, cfg)
sync = build_probe_sync(store, probe.probe_, cfg)

снятые = {}
for s in (io.open(ЖУРНАЛ, encoding="utf-8") if os.path.exists(ЖУРНАЛ) else []):
    try:
        z = json.loads(s)
    except Exception:                                          # noqa: BLE001
        continue
    if str(z.get("вердикт")) in СПРАШИВАЕМ and z.get("email"):
        снятые[str(z["email"]).lower()] = z
print(f"снятых с вердиктом «узнать не удалось»: {len(снятые)}")
if not снятые:
    raise SystemExit(0)


def текущие_вердикты():
    with store._lock:
        return {e: v for e, v in store._conn.execute(
            "SELECT lower(email), verdict FROM addr_probe")}


def вернуть(z):
    """Вернуть компанию в те группы, из которых её сняли."""
    rid = int(z["recipient_id"])
    сейчас = datetime.now(timezone.utc).isoformat()
    with store._lock:
        row = store._conn.execute(
            "SELECT COALESCE(segment,''), COALESCE(extra_json,'') "
            "FROM recipients WHERE id=?", (rid,)).fetchone()
    сегмент, сырое = (row or ("", ""))
    try:
        extra = json.loads(сырое) if сырое else {}
    except Exception:                                          # noqa: BLE001
        extra = {}
    гр = [g for g in (extra.get("gruppy") or [])]
    for g in (z.get("было_gruppy") or []):
        if g not in гр:
            гр.append(g)
    if ГРУППА not in гр and str(z.get("было_segment") or "") != ГРУППА:
        гр.append(ГРУППА)
    extra["gruppy"] = гр
    новый_сегмент = сегмент or str(z.get("было_segment") or "")
    with store.transaction() as conn:
        conn.execute(
            "UPDATE recipients SET segment=?, extra_json=?, updated_at=? "
            "WHERE id=?",
            (новый_сегмент, json.dumps(extra, ensure_ascii=False),
             сейчас, rid))
    with io.open(ВОЗВРАТЫ, "a", encoding="utf-8") as f:
        f.write(json.dumps({**z, "возвращён": сейчас}, ensure_ascii=False)
                + "\n")
        f.flush()
        os.fsync(f.fileno())


круг, итог = 0, Counter()
while time.time() - СТАРТ < ЛИМИТ_СЕК:
    круг += 1
    в = текущие_вердикты()
    ожили = [e for e in снятые if в.get(e) in ЖИВЫЕ]
    for e in ожили:
        try:
            вернуть(снятые.pop(e))
            итог["ВЕРНУЛИ В ПАРТИЮ"] += 1
        except Exception as ex:                                # noqa: BLE001
            print("  вернуть не вышло:", str(ex)[:90])
    ждут = [e for e in снятые if в.get(e) in СПРАШИВАЕМ or e not in в]
    print(f"[круг {круг}] осталось спросить {len(ждут)} | "
          f"вернули всего {итог['ВЕРНУЛИ В ПАРТИЮ']}")
    if not ждут:
        print("спрашивать больше некого")
        break

    порция = ждут[:ПОРЦИЯ]
    было = []
    try:
        сырое = sync._дроп("GET", "probe-zadanie.json").decode("utf-8",
                                                              "replace")
        v = json.loads(сырое)
        было = [str(x).strip().lower()
                for x in ((v.get("emails") if isinstance(v, dict) else v) or [])]
    except Exception as ex:                                    # noqa: BLE001
        print("  задания ещё нет:", str(ex)[:70])
    список, видели = [], set()
    for а in порция + было:
        if а and а not in видели:
            видели.add(а)
            список.append(а)
    sync._дроп("PUT", "probe-zadanie.json",
               json.dumps(список[:400], ensure_ascii=False).encode("utf-8"))
    try:
        sync._толкнуть(ПОРЦИЯ)
    except Exception as ex:                                    # noqa: BLE001
        print("  толкнуть не вышло:", str(ex)[:90])
    time.sleep(ПАУЗА)
    try:
        r = sync.забрать()
        print("  забрано:", {k: v for k, v in (r or {}).items()
                             if k in ("строк", "применено", "ошибка")})
    except Exception as ex:                                    # noqa: BLE001
        print("  забрать не вышло:", str(ex)[:90])

в = текущие_вердикты()
for e in [e for e in снятые if в.get(e) in ЖИВЫЕ]:
    try:
        вернуть(снятые.pop(e))
        итог["ВЕРНУЛИ В ПАРТИЮ"] += 1
    except Exception as ex:                                    # noqa: BLE001
        print("  вернуть не вышло:", str(ex)[:90])
print(f"\nитог: вернули в партию {итог['ВЕРНУЛИ В ПАРТИЮ']} | "
      f"осталось неопределённых {len(снятые)}")
print("журнал возвратов:", ВОЗВРАТЫ)
