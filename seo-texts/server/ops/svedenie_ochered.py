# -*- coding: utf-8 -*-
"""Сведение: сколько сгенерировали — сколько дошло до очереди отправки.

Владелец 25.08: «генерировали на опусе 337, потом 974 на соннет, а в очереди
отправки всего 700». Считаем не на память, а по durable-журналам генерации
(в них у каждой попытки есть модель, ок и номер карточки) плюс текущее
состояние sender.db. Каждое письмо попадает ровно в одну строку итога.
"""
import io
import json
import os
import sqlite3
from collections import Counter, defaultdict

ЖУРНАЛЫ = ["gen-partiya-935.jsonl", "deshevaya-partiya.jsonl",
           "tysyacha-sonnet.jsonl", "peregeneraciya-braka.jsonl",
           "peregeneraciya-meyer.jsonl", "perepisano-po-recenzii.jsonl",
           "perepisat-starye.jsonl", "dopisannye-zachiny.jsonl"]
КАТАЛОГ = r"C:\sender\_ops"


def день(ts):
    try:
        import datetime
        return datetime.datetime.fromtimestamp(float(ts)).strftime("%d.%m")
    except Exception:  # noqa: BLE001
        return "?"


# ── что записали журналы генерации ────────────────────────────────────────
письма = {}            # review_id -> (модель, день, журнал)
без_очереди = Counter()  # написано, но карточки нет
for имя in ЖУРНАЛЫ:
    п = os.path.join(КАТАЛОГ, имя)
    if not os.path.exists(п):
        continue
    for с in io.open(п, encoding="utf-8", errors="replace"):
        с = с.strip()
        if not с or not с.startswith("{"):
            continue
        try:
            з = json.loads(с)
        except Exception:  # noqa: BLE001
            continue
        rid = з.get("review_id")
        мод = з.get("модель") or ("механическая схема"
                                  if имя == "deshevaya-partiya.jsonl" else "?")
        д = день(з.get("ts"))
        if rid:
            письма[int(rid)] = (мод, д, имя)
        elif з.get("ок") or з.get("тело"):
            без_очереди["%s / %s" % (мод, д)] += 1

print("=== ЖУРНАЛЫ ГЕНЕРАЦИИ ===")
print("писем с карточкой в очереди подтверждения: %d" % len(письма))
if без_очереди:
    print("написано, но карточка не создалась:")
    for к, н in без_очереди.most_common(10):
        print("   %-46s %5d" % (к, н))

# ── где они теперь ────────────────────────────────────────────────────────
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row


def куда(карта, письмо, причина):
    """Одна корзина на письмо — по факту, а не по намерению."""
    if письмо == "sent":
        return "ОТПРАВЛЕНО"
    if письмо in ("scheduled", "sending", "sending_live"):
        return "В ОЧЕРЕДИ ОТПРАВКИ"
    if карта in ("pending", "edited"):
        return "ждёт подтверждения"
    if письмо == "failed":
        return "сорвалось при отправке"
    п = (причина or "").lower()
    if карта == "skipped" or письмо == "skipped":
        if "механическ" in п:
            return "снято: механическая схема"
        if "адрес" in п or "ящик" in п or "mx" in п or "неясно" in п:
            return "снято: адрес"
        if "не тому" in п or "адресат" in п:
            return "снято: не тот адресат"
        if "линз" in п:
            return "снято: линза"
        if п:
            return "снято: " + п[:34]
        return "снято: без пометки"
    return "прочее (карта %s / письмо %s)" % (карта, письмо)


итог = defaultdict(Counter)      # (модель, день) -> корзина -> N
пропало = 0
for rid, (мод, д, _ж) in письма.items():
    р = c.execute("SELECT cr.status st, cr.reason rs, COALESCE(m.status,'-') ms "
                  "  FROM confirm_reviews cr "
                  "  LEFT JOIN messages m ON m.id=cr.message_id "
                  " WHERE cr.id=?", (rid,)).fetchone()
    if not р:
        пропало += 1
        continue
    итог[(мод, д)][куда(р["st"], р["ms"], р["rs"])] += 1

всего = Counter()
print("\n=== СУДЬБА КАЖДОЙ ПАРТИИ ===")
for (мод, д) in sorted(итог, key=lambda k: (k[1], k[0])):
    ст = итог[(мод, д)]
    print("\n%s, %s — написано %d" % (мод, д, sum(ст.values())))
    for к, н in ст.most_common():
        print("    %-40s %5d" % (к, н))
        всего[к] += н
if пропало:
    print("\nкарточка исчезла из базы: %d" % пропало)

print("\n=== ИТОГО ПО ВСЕМ ПАРТИЯМ ===")
for к, н in всего.most_common():
    print("  %-42s %5d" % (к, н))
print("  %-42s %5d" % ("ВСЕГО НАПИСАНО", sum(всего.values())))

# ── очередь целиком, включая письма не из этих журналов ───────────────────
print("\n=== ОЧЕРЕДЬ ОТПРАВКИ ЦЕЛИКОМ (sender.db) ===")
for р in c.execute("SELECT status, COUNT(*) n FROM messages GROUP BY status "
                   "ORDER BY n DESC"):
    print("  письма %-22s %5d" % (р["status"], р["n"]))
свои = c.execute(
    "SELECT COUNT(*) FROM messages WHERE status IN ('scheduled','sending')"
).fetchone()[0]
из_журналов = sum(1 for rid in письма
                  if (c.execute("SELECT COALESCE(m.status,'-') s FROM confirm_reviews cr "
                                "  LEFT JOIN messages m ON m.id=cr.message_id "
                                " WHERE cr.id=?", (rid,)).fetchone() or {"s": "-"})["s"]
                  in ("scheduled", "sending"))
print("  из них опознано журналами генерации: %d из %d" % (из_журналов, свои))
