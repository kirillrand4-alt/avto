# -*- coding: utf-8 -*-
"""Когорты: каждая компания ровно в одном месяце — по ПЕРВОМУ письму ей.

Так столбцы складываются: охват даёт общее число компаний, Битрикс — 19,
а не 21. Компания, которой писали и в августе, и в сентябре, целиком
относится к августу: именно тогда мы её тронули впервые.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

МЕЙЕР = ("optic-sort.ru", "sort-systems.ru", "zernosort.ru", "food-sort.ru",
         "sorting-systems.ru", "rentgen-control.ru", "optical-sort.ru",
         "rentgen-inspection.ru", "inspection-systems.ru")
store = Store(r"C:\sender\sender.db")
усл = " OR ".join("m.mailbox_id LIKE '%%%s'" % д for д in МЕЙЕР)

with store._lock:
    c = store._conn
    # месяц ПЕРВОГО письма каждой компании
    когорта = {}
    писем_мес = Counter()
    for р in c.execute(
            "SELECT r.inn, MIN(substr(m.sent_at,1,7)) м, COUNT(*) n "
            "  FROM messages m JOIN recipients r ON m.recipient_id = r.id "
            " WHERE m.status='sent' AND m.sent_at >= '2026-08-01' AND (%s) "
            "   AND COALESCE(r.inn,'')<>'' GROUP BY r.inn" % усл):
        когорта[str(р["inn"]).strip()] = str(р["м"])
    # письма считаем по месяцу отправки (это про нагрузку, не про когорту)
    for р in c.execute(
            "SELECT substr(m.sent_at,1,7) м, COUNT(*) n FROM messages m "
            " WHERE m.status='sent' AND m.sent_at >= '2026-08-01' AND (%s) "
            " GROUP BY 1" % усл):
        писем_мес[str(р["м"])] = int(р["n"])

    ответили = {str(р["inn"]).strip() for р in c.execute(
        "SELECT DISTINCT r.inn FROM events e "
        "  JOIN messages m ON e.message_id = m.id "
        "  JOIN recipients r ON m.recipient_id = r.id "
        " WHERE e.event_type='reply' AND m.status='sent' "
        "   AND m.sent_at >= '2026-08-01' AND (%s)" % усл) if р["inn"]}

    бит = {р["lead_id"] for р in c.execute(
        "SELECT DISTINCT lead_id FROM lead_events WHERE to_status='in_bitrix'")}
    for р in c.execute("SELECT id FROM leads WHERE status='in_bitrix'"):
        бит.add(р["id"])
    инн_бит = {str(р["inn"]).strip() for р in c.execute(
        "SELECT id, inn FROM leads") if р["id"] in бит and р["inn"]}

свод = {}
for инн, м in когорта.items():
    д = свод.setdefault(м, {"охват": 0, "отв": 0, "бит": 0})
    д["охват"] += 1
    if инн in ответили:
        д["отв"] += 1
    if инн in инн_бит:
        д["бит"] += 1

print("   %-10s %8s %10s %9s %9s %10s %9s %10s"
      % ("когорта", "писем", "компаний", "ответили", "% ответа",
         "в Битрикс", "% от всех", "% от отв."))
итог = {"охват": 0, "отв": 0, "бит": 0, "писем": 0}
for м in sorted(свод):
    д = свод[м]
    п = писем_мес.get(м, 0)
    print("   %-10s %8d %10d %9d %8.2f%% %10d %8.2f%% %9.1f%%"
          % (м, п, д["охват"], д["отв"],
             100.0 * д["отв"] / д["охват"] if д["охват"] else 0, д["бит"],
             100.0 * д["бит"] / д["охват"] if д["охват"] else 0,
             100.0 * д["бит"] / д["отв"] if д["отв"] else 0))
    for к in ("охват", "отв", "бит"):
        итог[к] += д[к]
    итог["писем"] += п
print("")
print("=" * 74)
print("=== КОГОРТЫ ПО ПЕРВОМУ ПИСЬМУ ===")
print("   %-10s %8d %10d %9d %8.2f%% %10d %8.2f%% %9.1f%%"
      % ("ИТОГО", итог["писем"], итог["охват"], итог["отв"],
         100.0 * итог["отв"] / итог["охват"] if итог["охват"] else 0,
         итог["бит"], 100.0 * итог["бит"] / итог["охват"] if итог["охват"] else 0,
         100.0 * итог["бит"] / итог["отв"] if итог["отв"] else 0))
