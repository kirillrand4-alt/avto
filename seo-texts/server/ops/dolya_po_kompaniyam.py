# -*- coding: utf-8 -*-
"""Проценты по КОМПАНИЯМ, а не по письмам. Всё на одной единице — ИНН.

Раньше «охвачено» считалось по ИНН, а «ответили» по получателям: у одной
компании бывает несколько адресов, и доля получалась завышенной. Здесь
обе величины и Битрикс — строго по ИНН.
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

МЕЙЕР = ("optic-sort.ru", "sort-systems.ru", "zernosort.ru", "food-sort.ru",
         "sorting-systems.ru", "rentgen-control.ru", "optical-sort.ru",
         "rentgen-inspection.ru", "inspection-systems.ru")
МЕСЯЦЫ = ("2026-08", "2026-09")
store = Store(r"C:\sender\sender.db")
усл = " OR ".join("m.mailbox_id LIKE '%%%s'" % д for д in МЕЙЕР)

строки = []
with store._lock:
    c = store._conn
    в_битриксе = {р["lead_id"] for р in c.execute(
        "SELECT DISTINCT lead_id FROM lead_events WHERE to_status='in_bitrix'")}
    for р in c.execute("SELECT id FROM leads WHERE status='in_bitrix'"):
        в_битриксе.add(р["id"])
    # ИНН лидов, доехавших до Битрикса
    инн_бит = set()
    for р in c.execute("SELECT id, inn FROM leads"):
        if р["id"] in в_битриксе and р["inn"]:
            инн_бит.add(str(р["inn"]).strip())

    for м in МЕСЯЦЫ:
        охват = {str(р["inn"]).strip() for р in c.execute(
            "SELECT DISTINCT r.inn FROM messages m "
            "  JOIN recipients r ON m.recipient_id = r.id "
            " WHERE m.status='sent' AND substr(m.sent_at,1,7)=? AND (%s)"
            % усл, (м,)) if р["inn"]}
        ответили = {str(р["inn"]).strip() for р in c.execute(
            "SELECT DISTINCT r.inn FROM events e "
            "  JOIN messages m ON e.message_id = m.id "
            "  JOIN recipients r ON m.recipient_id = r.id "
            " WHERE e.event_type='reply' AND m.status='sent' "
            "   AND substr(m.sent_at,1,7)=? AND (%s)" % усл, (м,)) if р["inn"]}
        строки.append((м, охват, ответили, охват & инн_бит))

print("   %-10s %10s %10s %8s %10s %8s %9s"
      % ("месяц", "охвачено", "ответили", "% ответа", "в Битрикс",
         "% от всех", "% от отв."))
for м, о, отв, б in строки:
    print("   %-10s %10d %10d %7.2f%% %10d %7.2f%% %8.1f%%"
          % (м, len(о), len(отв), 100.0 * len(отв) / len(о) if о else 0,
             len(б), 100.0 * len(б) / len(о) if о else 0,
             100.0 * len(б) / len(отв) if отв else 0))

пересеч = строки[0][0] and (строки[0][1] & строки[1][1])
print("")
print("=" * 74)
print("=== ДОЛИ ПО КОМПАНИЯМ ===")
print("   компаний в обоих месяцах (учтены дважды): %d" % len(пересеч))
общий_охват = строки[0][1] | строки[1][1]
общий_отв = строки[0][2] | строки[1][2]
общий_бит = строки[0][3] | строки[1][3]
print("   за оба месяца без двойного счёта:")
print("      охвачено %d, ответили %d (%.2f%%), в Битрикс %d (%.2f%%)"
      % (len(общий_охват), len(общий_отв),
         100.0 * len(общий_отв) / len(общий_охват) if общий_охват else 0,
         len(общий_бит),
         100.0 * len(общий_бит) / len(общий_охват) if общий_охват else 0))
