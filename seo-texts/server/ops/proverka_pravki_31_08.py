# -*- coding: utf-8 -*-
"""Проверка правки increment_sent на синтетическом ящике.

Никаких писем не отправляет. Берёт заведомо несуществующий mailbox_id,
зовёт increment_sent и смотрит: раньше был StoreError, теперь должна
завестись строка. В конце тестовую строку удаляет."""
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

ТЕСТ = "__proverka_pravki__@example.invalid"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
было = s.execute("SELECT COUNT(*) n FROM mailbox_state WHERE mailbox_id=?",
                 (ТЕСТ,)).fetchone()["n"]
print("=== ДО ===")
print("  строк состояния у тестового ящика: %d" % было)

теперь = datetime.now(timezone.utc)
print("\n=== ЗОВЁМ increment_sent НА ЯЩИК БЕЗ СТРОКИ ===")
try:
    st = store.increment_sent(ТЕСТ, now=теперь, day_key=теперь.strftime("%Y-%m-%d"))
    print("  ИСКЛЮЧЕНИЯ НЕТ — правка работает")
    print("  вернулось: sent_today=%s sent_total=%s ramp_day=%s day_key=%s"
          % (st.sent_today, st.sent_total, st.ramp_day, st.day_key))
except Exception as ex:
    print("  ИСКЛЮЧЕНИЕ %s: %s" % (type(ex).__name__, str(ex)[:100]))
    print("  ПРАВКА НЕ РАБОТАЕТ (или процесс взял старый код)")

s2 = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s2.row_factory = sqlite3.Row
р = s2.execute("SELECT * FROM mailbox_state WHERE mailbox_id=?", (ТЕСТ,)).fetchone()
print("\n=== ПОСЛЕ ===")
if р:
    print("  строка ЗАВЕЛАСЬ: sent_today=%s sent_total=%s ramp_day=%s paused=%s"
          % (р["sent_today"], р["sent_total"], р["ramp_day"], р["paused"]))
else:
    print("  строки нет")

# убираем за собой
w = sqlite3.connect(r"C:\sender\sender.db")
c = w.cursor()
c.execute("DELETE FROM mailbox_state WHERE mailbox_id=?", (ТЕСТ,))
w.commit()
print("\n=== ИТОГ ===")
print("  тестовая строка удалена: %d" % c.rowcount)
ост = s2.execute("SELECT COUNT(*) n FROM mailbox_state").fetchone()["n"]
print("  всего строк mailbox_state осталось: %d (должно быть 33)" % ост)
