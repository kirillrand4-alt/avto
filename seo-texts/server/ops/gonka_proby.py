# -*- coding: utf-8 -*-
"""Насколько широка щель: сколько писем ушло раньше вердикта пробы.

Проба асинхронна: письмо может уйти до того, как вердикт вернётся с VPS.
Считаем по всем сегодняшним отправкам, у скольких вердикт был ДО отправки,
у скольких появился ПОСЛЕ, и у скольких его нет до сих пор.
"""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

итог = Counter()
задержки = []
for р in c.execute(
        "SELECT m.sent_at, r.email FROM messages m "
        "  JOIN recipients r ON r.id=m.recipient_id "
        " WHERE m.status='sent' AND substr(COALESCE(m.sent_at,''),1,10)=date('now')"):
    адрес = str(р["email"] or "").lower()
    отпр = str(р["sent_at"] or "")[:19]
    п = c.execute("SELECT verdict, source, ts FROM addr_probe "
                  " WHERE lower(email)=? ORDER BY ts LIMIT 1", (адрес,)).fetchone()
    if not п:
        итог["вердикта нет до сих пор"] += 1
    elif str(п["ts"])[:19] < отпр:
        итог["вердикт БЫЛ до отправки"] += 1
    else:
        итог["вердикт появился ПОСЛЕ"] += 1
        задержки.append((отпр, str(п["ts"])[:19], адрес, п["verdict"],
                         п["source"] or "-"))

всего = sum(итог.values())
print("=== ОТПРАВЛЕНО СЕГОДНЯ: %d ===" % всего)
for к, н in итог.most_common():
    print("  %-28s %5d  (%.1f%%)" % (к, н, 100.0 * н / всего if всего else 0))

print("\n=== ИЗ «ПОСЛЕ»: ЧТО ЗА ВЕРДИКТЫ ===")
по_вердикту = Counter((в, и) for _о, _т, _а, в, и in задержки)
for (в, и), н in по_вердикту.most_common(8):
    метка = "  ← письмо надо было снять" if в in ("нет ящика", "нет MX") else ""
    print("  %-16s [%-12s] %4d%s" % (в, и, н, метка))

print("\n=== ПРИМЕРЫ ОПОЗДАНИЯ ===")
for о, т, а, в, и in задержки[:8]:
    print("  %-30s отправлено %s, вердикт %s (%s)"
          % (а[:30], о[11:], т[11:], в))

print("\n=== СКОЛЬКО СЕЙЧАС ЖДЁТ ОТПРАВКИ БЕЗ ВЕРДИКТА ===")
н = c.execute(
    "SELECT COUNT(*) n FROM confirm_reviews cr "
    "  JOIN recipients r ON r.id=cr.recipient_id "
    "  LEFT JOIN addr_probe p ON lower(p.email)=lower(r.email) "
    " WHERE cr.status IN ('pending','approved') AND p.email IS NULL").fetchone()["n"]
print("  карточек без вердикта в очереди: %d" % н)
