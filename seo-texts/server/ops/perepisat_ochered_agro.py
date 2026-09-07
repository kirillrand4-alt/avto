# -*- coding: utf-8 -*-
"""Переписать тексты уже стоящих в очереди писем партии «Агро зерно 2026».

Правило подстановки названия меняется по ходу проверки глазами, а карточка
в очереди идемпотентна по dedup_key: повторный submit ничего не перезапишет.
Поэтому правим строки очереди напрямую - но ТОЛЬКО свои и ТОЛЬКО pending:
карточку, которую оператор уже подтвердил или отправил, трогать нельзя.

    python perepisat_ochered_agro.py            # вхолостую
    python perepisat_ochered_agro.py --primenit
"""
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sender.store import Store                                 # noqa: E402
from imya_v_pismo import итоговое_имя                          # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\agro-ochered.jsonl"
ИМЕНА = r"C:\sender\_ops\agro-imena.jsonl"
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv

ТЕЛО = """Добрый день!

Меня зовут ИМЯ_ОТПРАВИТЕЛЯ, представляю компанию «Руспром Meyer». Работаю с зерновыми хозяйствами по вопросам оптической сортировки зерна.

{зачин} выращивает зерновые культуры, поэтому обращаюсь по теме доведения товарных партий до требуемого качества.

Для таких задач применяется фотосепаратор: машина отбраковывает минеральные, сорные, зерновые примеси, проросшие, повреждённые зёрна. Наше оборудование быстро перенастраивается в зависимости от культуры и задачи двумя кнопками.

Мы проводим тестовые сортировки в наших демо залах в любом удобном формате - лично или дистанционно (предоставляя видеоматериал сортировки).

Подскажите, актуальна ли для вас сейчас задача по очистке сырья или подготовке семенного материала?

С уважением,"""

имена = {}
for с in io.open(ИМЕНА, encoding="utf-8", errors="replace"):
    с = с.strip()
    if с:
        try:
            z = json.loads(с)
            if z.get("сыро"):
                имена[z["сыро"]] = (z.get("имя"), bool(z.get("человек")))
        except Exception:                                      # noqa: BLE001
            pass

карточки = {}
if os.path.exists(ЖУРНАЛ):
    for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
        с = с.strip()
        if not с:
            continue
        try:
            z = json.loads(с)
        except Exception:                                      # noqa: BLE001
            continue
        if z.get("review_id"):
            карточки[int(z["review_id"])] = z

store = Store(r"C:\sender\sender.db")
счёт = Counter({"карточек в журнале": len(карточки)})
правки = []
with store._lock:
    for rid, z in карточки.items():
        стр = store._conn.execute(
            "SELECT status, body FROM confirm_reviews WHERE id=?",
            (rid,)).fetchone()
        if стр is None:
            счёт["карточки нет в базе"] += 1
            continue
        статус = str(стр["status"])
        if статус != "pending":
            счёт["не pending: " + статус] += 1
            continue
        сыро = " ".join(str(z.get("имя_реестра") or "").split())
        пара = имена.get(сыро)
        if not пара:
            счёт["названия нет в разборе"] += 1
            continue
        подл, _вид = итоговое_имя(пара[0], пара[1])
        новое = ТЕЛО.format(зачин=подл)
        if новое == str(стр["body"] or ""):
            счёт["уже правильное"] += 1
            continue
        правки.append((rid, сыро, подл, новое))
        счёт["К ПРАВКЕ"] += 1

if ПРИМЕНИТЬ and правки:
    with store.transaction() as conn:
        for rid, _с, _п, новое in правки:
            conn.execute("UPDATE confirm_reviews SET body=?, updated_at="
                         "datetime('now') WHERE id=? AND status='pending'",
                         (новое, rid))
    счёт["ПЕРЕПИСАНО"] = len(правки)

print("--- что меняется (до 20) ---")
for rid, сыро, подл, _н in правки[:20]:
    print("   %-8s %-34s → %s" % (rid, сыро[:34], подл))
print("")
print("=" * 74)
print("=== ПЕРЕПИСЬ ОЧЕРЕДИ: %s ==="
      % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН"))
for к, в in счёт.most_common():
    print("   %-34s %6d" % (к, в))
