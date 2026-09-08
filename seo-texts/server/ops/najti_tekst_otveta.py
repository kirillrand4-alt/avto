# -*- coding: utf-8 -*-
"""Поиск текста автоответа по всей базе: где вообще лежат тела входящих."""
import re, sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

КУСКИ = ("Информируем вас о том", "Агро-Х", "агро-хорс", "6316219819",
         "agro-hors")
store = Store(r"C:\sender\sender.db")
АДРЕС = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
находки = []
with store._lock:
    таблицы = [r[0] for r in store._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    for т in таблицы:
        try:
            кол = [c[1] for c in store._conn.execute("PRAGMA table_info(%s)" % т)]
        except Exception:                                       # noqa: BLE001
            continue
        for c in кол:
            for к in КУСКИ:
                try:
                    n = store._conn.execute(
                        "SELECT COUNT(*) FROM %s WHERE %s LIKE ?" % (т, c),
                        ("%" + к + "%",)).fetchone()[0]
                except Exception:                               # noqa: BLE001
                    break
                if n:
                    находки.append((т, c, к, n))
for т, c, к, n in находки:
    print("   %-20s %-18s «%s» → %d строк" % (т, c, к, n))
print("")
print("=" * 74)
print("=== ГДЕ ЛЕЖИТ АВТООТВЕТ ===")
if not находки:
    print("нигде в sender.db не нашлось — тело входящего живёт вне этой базы")
