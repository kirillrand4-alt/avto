# -*- coding: utf-8 -*-
"""Проверка, что у снятых ЦЗН-карточек и письмо не осталось живым.

confirm_decide переводит messages в skipped одной транзакцией с решением,
поэтому второй шаг и вернул ноль. Но верить этому на слово нельзя: живое
письмо при снятой карточке - это ровно та дыра, когда оператор писем не
видит, а автоотправка их шлёт.
"""
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                 # noqa: E402

ТЕМА = "Для качества: вопрос по сортировке зерна"
ПРИЗНАК = "адрес центра занятости"
store = Store(r"C:\sender\sender.db")
счёт = Counter()
опасные = []
with store._lock:
    for р in store._conn.execute(
            "SELECT id, email, status, message_id, reason FROM confirm_reviews "
            " WHERE subject=? AND reason LIKE ?", (ТЕМА, "%" + ПРИЗНАК + "%")):
        счёт["карточек снято"] += 1
        if not р["message_id"]:
            счёт["без письма"] += 1
            continue
        м = store._conn.execute("SELECT status FROM messages WHERE id=?",
                                (int(р["message_id"]),)).fetchone()
        с = str(м["status"]) if м else "нет строки"
        счёт["письмо: " + с] += 1
        if с not in ("skipped", "sent", "failed", "нет строки"):
            опасные.append((р["id"], р["email"], с))
for i, а, с in опасные[:20]:
    print("   ЖИВОЕ ПИСЬМО: карточка %s %s → %s" % (i, а, с))
print("")
print("=" * 70)
print("=== СНЯТЫЕ ЦЗН: ПРОВЕРКА ПИСЕМ ===")
for к, в in счёт.most_common():
    print("   %-28s %5d" % (к, в))
print("осталось живых писем при снятой карточке: %d" % len(опасные))
