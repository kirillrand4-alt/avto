# -*- coding: utf-8 -*-
"""Сколько карточек партии осталось со старым текстом."""
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                 # noqa: E402

ТЕМА = "для качества: вопрос по сортировке зерна"
НОВЫЙ = "решето и аспирация"
СТАРЫЙ = "доведения товарных партий"
store = Store(r"C:\sender\sender.db")
счёт = Counter()
примеры = []
with store._lock:
    for р in store._conn.execute(
            "SELECT id, status, email, body FROM confirm_reviews WHERE subject=?",
            (ТЕМА,)):
        т = str(р["body"] or "")
        вид = ("новый" if НОВЫЙ in т else "СТАРЫЙ" if СТАРЫЙ in т else "иной")
        счёт["%s / %s" % (str(р["status"]), вид)] += 1
        if вид != "новый" and str(р["status"]) == "pending":
            примеры.append((р["id"], р["email"]))
    # ГЛАВНАЯ ПРОВЕРКА. Правка тела карточки бесполезна, если у письма уже
    # лежит собранный текст: на отправку уйдёт он, а не то, что видит
    # оператор. Смотрим body_rendered именно у писем НАШЕЙ партии.
    свои = store._conn.execute(
        """SELECT m.status, m.body_rendered
             FROM messages m JOIN confirm_reviews c ON c.message_id = m.id
            WHERE c.subject=?""", (ТЕМА,)).fetchall()
    собрано = Counter()
    старых_собранных = []
    for м in свои:
        т = str(м["body_rendered"] or "")
        if not т.strip():
            собрано["тело пустое (соберётся на отправке)"] += 1
            continue
        собрано["тело уже собрано: " + ("новое" if НОВЫЙ in т else "СТАРОЕ")] += 1
        if НОВЫЙ not in т:
            старых_собранных.append(str(м["status"]))
for i, а in примеры[:10]:
    print("   pending со старым текстом: %s %s" % (i, а))
print("")
print("=" * 70)
print("=== ТЕКСТ В КАРТОЧКАХ ПАРТИИ ===")
for к, в in счёт.most_common():
    print("   %-24s %5d" % (к, в))
print("")
print("письма партии:")
for к, в in собрано.most_common():
    print("   %-42s %5d" % (к, в))
if старых_собранных:
    print("   ОПАСНО: собранных со старым текстом %d, статусы: %s"
          % (len(старых_собранных), Counter(старых_собранных).most_common()))
