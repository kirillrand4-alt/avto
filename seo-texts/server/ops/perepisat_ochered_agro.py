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
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sender.store import Store                                 # noqa: E402
from imya_v_pismo import итоговое_имя                          # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\agro-ochered.jsonl"
# СНИМОК ДО ПЕРЕЗАПИСИ. Текст письма правится по живой очереди, и вернуть
# прежний надо уметь не «пересобрав по шаблону», а буквально: шаблонов было
# уже несколько, и какой стоял в конкретной карточке - вопрос без ответа,
# если не сохранить. Пишем с fsync, файл на снимок.
СНИМОК = (r"C:\sender\_ops\agro-ochered-do-zameny-"
          + time.strftime("%m%d-%H%M%S") + ".jsonl")
ИМЕНА = r"C:\sender\_ops\agro-imena.jsonl"
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv

ТЕЛО = """Добрый день!

Меня зовут ИМЯ_ОТПРАВИТЕЛЯ, представляю компанию «Руспром Meyer». Работаю с зерновыми хозяйствами по вопросам оптической сортировки зерна.

{зачин} выращивает зерновые культуры, поэтому пишу по задаче, которую решето и аспирация не закрывают: зерно с потемневшим зародышем, головнёй, фузариозом, просто отличающееся по цвету. На приёмке это идёт в сорную и зерновую примесь, и партия садится по классу.

Такое отбирает фотосепаратор: он смотрит на каждое зерно по цвету и отделяет повреждённые, проросшие и битые вместе с минеральной и сорной примесью. Важнее другое - вместе с ними он не выбрасывает нормальное зерно, поэтому в товарной фракции его остаётся больше, чем после механической очистки.

Экономика зависит от культуры, объёмов и того, насколько грязное зерно на входе: в одних хозяйствах машина окупалась за несколько недель, в других за сезон.

Поэтому предлагаю не считать на словах, а проверить на вашем зерне: проведём тестовую сортировку и покажем результат до и после. Можно приехать в наш демо-зал лично, можно дистанционно - пришлём видео процесса и результат.

Подскажите, актуальна ли сейчас задача по очистке зерна или подготовке семян? Если да, достаточно назвать культуру и примерный объём - предложу подходящее оборудование и формат теста.

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
    with io.open(СНИМОК, "w", encoding="utf-8") as _ф:
        for rid, сыро, подл, _н in правки:
            with store._lock:
                _б = store._conn.execute(
                    "SELECT body FROM confirm_reviews WHERE id=?",
                    (rid,)).fetchone()
            _ф.write(json.dumps({"review_id": rid, "имя_реестра": сыро,
                                 "тело_до": str(_б["body"] if _б else "")},
                                ensure_ascii=False) + "\n")
        _ф.flush()
        os.fsync(_ф.fileno())
    счёт["снимок сохранён"] = len(правки)
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
