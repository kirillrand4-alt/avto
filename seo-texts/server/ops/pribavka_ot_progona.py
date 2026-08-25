# -*- coding: utf-8 -*-
"""Точная прибавка от сегодняшнего прогона: сколько писем и где они лежат.

Прогон стартовал 13:41 по машине (10:41 UTC). Всё, что создано после,
принадлежит ему: блок Meyer, затем КЦ. Считаем не «сколько написали», а
где эти письма сейчас — в очереди отправки, в ожидании подтверждения или
уже сняты.
"""
import sqlite3
from collections import Counter

СТАРТ = "2026-08-25 10:41"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row

print("=== ОЧЕРЕДЬ ОТПРАВКИ СЕЙЧАС ===")
for р in c.execute("SELECT status, COUNT(*) n FROM messages "
                   " GROUP BY status ORDER BY n DESC"):
    print("   письма %-16s %5d" % (р["status"], р["n"]))

print("\n=== КАРТОЧКИ, СОЗДАННЫЕ ПРОГОНОМ (после %s) ===" % СТАРТ)
ряды = c.execute(
    "SELECT cr.status cs, COALESCE(m.status,'нет письма') ms, "
    "       COALESCE(r.segment,'') сег, r.inn, m.subject "
    "  FROM confirm_reviews cr "
    "  LEFT JOIN messages m ON m.id=cr.message_id "
    "  LEFT JOIN recipients r ON r.id=cr.recipient_id "
    " WHERE cr.created_at >= ?", (СТАРТ,)).fetchall()
print("всего создано: %d" % len(ряды))
for к, н in Counter("карта %s / письмо %s" % (р["cs"], р["ms"])
                    for р in ряды).most_common():
    print("   %-42s %5d" % (к, н))

# Направление считаем по теме письма: у Meyer свои слова.
МЕЙЕР = ("контрол", "рентген", "фотосепаратор", "включени", "инспекц",
         "сортиров", "качеств")


def напр(тема):
    т = str(тема or "").lower()
    return "Meyer" if any(с in т for с in МЕЙЕР) else "КЦ"


print("\n=== ПО НАПРАВЛЕНИЯМ (по теме письма) ===")
for к, н in Counter(напр(р["subject"]) for р in ряды).most_common():
    print("   %-10s %5d" % (к, н))

print("\n=== СКОЛЬКО ИЗ НИХ УЖЕ В ОЧЕРЕДИ ОТПРАВКИ ===")
в_очереди = [р for р in ряды if р["ms"] in ("scheduled", "sending")]
print("   в очереди: %d" % len(в_очереди))
for к, н in Counter(напр(р["subject"]) for р in в_очереди).most_common():
    print("      %-10s %5d" % (к, н))
ждут = [р for р in ряды if р["cs"] in ("pending", "edited")]
print("   ждут подтверждения: %d" % len(ждут))
сняты = [р for р in ряды if р["cs"] == "skipped" or р["ms"] == "skipped"]
print("   сняты: %d" % len(сняты))
