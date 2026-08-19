# -*- coding: utf-8 -*-
"""Что происходит с письмом, если направление оказалось неверным.

Владелец: «а если проставлено заранее в итоге не верно окажется, он
перенесётся?». Переноса между кампаниями в коде нет — линза только СНИМАЕТ
письмо. Здесь считаем цену этого: сколько писем снято по профилю и что
стало с их компаниями.

Ключевая развилка резюма генерации: компания считается отработанной, если
в журнале есть ТЕЛО письма. Брак генерации тела не даёт — компания
вернётся в следующий круг. А снятие ПОСЛЕ генерации даёт: тело записано,
компания помечена «письмо уже есть» и в новую партию не попадёт никогда.
"""
import io
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                       # noqa: E402
from sender.store import Store                                         # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

print("== снятия по профилю (панельная линза) ==")
with store._lock:
    try:
        всего = store._conn.execute(
            "SELECT COUNT(*) FROM linza_otkazy").fetchone()[0]
        уник = store._conn.execute(
            "SELECT COUNT(DISTINCT review_id) FROM linza_otkazy").fetchone()[0]
        дважды = store._conn.execute(
            "SELECT COUNT(*) FROM (SELECT review_id FROM linza_otkazy "
            "GROUP BY review_id HAVING COUNT(*)>=2)").fetchone()[0]
    except Exception as ex:                                            # noqa: BLE001
        всего = уник = дважды = 0
        print("  таблицы отказов ещё нет:", str(ex)[:80])
print(f"  отказов линзы всего {всего}, писем {уник}, "
      f"снято (два и более) {дважды}")

print("\n== письма, снятые как «не наш адресат» ==")
with store._lock:
    снятые = store._conn.execute(
        "SELECT campaign_id, COUNT(*) FROM confirm_reviews "
        "WHERE status='skipped' AND (reason LIKE '%не наш%' "
        "   OR reason LIKE '%вне профиля%' OR reason LIKE '%не покупатель%') "
        "GROUP BY campaign_id").fetchall()
    всего_снято = sum(int(b) for _a, b in снятые)
print(f"  по кампаниям: {{{', '.join(f'{int(a)}: {int(b)}' for a, b in снятые)}}}"
      f"  всего {всего_снято}")

# ---- вернутся ли их компании в новую партию ------------------------------ #
сделано, брак_без_тела = set(), set()
for s in io.open(ЖУРНАЛ, encoding="utf-8"):
    try:
        z = json.loads(s)
    except Exception:                                                  # noqa: BLE001
        continue
    inn = str(z.get("inn") or "")
    if not inn:
        continue
    if z.get("ок") or z.get("тело"):
        сделано.add(inn)
    elif z.get("тело_брака"):
        брак_без_тела.add(inn)
брак_без_тела -= сделано

print("\n== резюм генерации ==")
print(f"  компаний с ГОТОВЫМ телом (в новую партию НЕ попадут): {len(сделано)}")
print(f"  компаний только с браком (вернутся в следующий круг): "
      f"{len(брак_без_тела)}")

print("\n== сколько снятых по профилю уже не вернутся ==")
with store._lock:
    инн_снятых = [r[0] for r in store._conn.execute(
        "SELECT DISTINCT r.inn FROM confirm_reviews c "
        "LEFT JOIN recipients r ON r.id=c.recipient_id "
        "WHERE c.status='skipped' AND (c.reason LIKE '%не наш%' "
        "   OR c.reason LIKE '%вне профиля%' OR c.reason LIKE '%не покупатель%')"
    ).fetchall() if r[0]]
потеряны = [i for i in инн_снятых
            if "".join(c for c in str(i) if c.isdigit()) in сделано]
print(f"  снято по профилю компаний: {len(инн_снятых)}")
print(f"  из них с записанным телом -> ВЫБЫЛИ НАВСЕГДА: {len(потеряны)}")
print(f"  остальные вернутся в следующий круг: "
      f"{len(инн_снятых) - len(потеряны)}")
