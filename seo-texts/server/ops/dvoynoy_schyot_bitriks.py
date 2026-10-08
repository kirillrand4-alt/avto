# -*- coding: utf-8 -*-
"""Кто учтён дважды: 13 + 8 = 21 против 19 без двойного счёта."""
import sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

МЕЙЕР = ("optic-sort.ru", "sort-systems.ru", "zernosort.ru", "food-sort.ru",
         "sorting-systems.ru", "rentgen-control.ru", "optical-sort.ru",
         "rentgen-inspection.ru", "inspection-systems.ru")
store = Store(r"C:\sender\sender.db")
усл = " OR ".join("m.mailbox_id LIKE '%%%s'" % д for д in МЕЙЕР)
with store._lock:
    c = store._conn
    бит = {р["lead_id"] for р in c.execute(
        "SELECT DISTINCT lead_id FROM lead_events WHERE to_status='in_bitrix'")}
    for р in c.execute("SELECT id FROM leads WHERE status='in_bitrix'"):
        бит.add(р["id"])
    инн_бит = {}
    for р in c.execute("SELECT id, inn, company_name FROM leads"):
        if р["id"] in бит and р["inn"]:
            инн_бит[str(р["inn"]).strip()] = (р["id"], р["company_name"])

    месяцы = {}
    for м in ("2026-08", "2026-09"):
        месяцы[м] = {str(р["inn"]).strip() for р in c.execute(
            "SELECT DISTINCT r.inn FROM messages m "
            "  JOIN recipients r ON m.recipient_id = r.id "
            " WHERE m.status='sent' AND substr(m.sent_at,1,7)=? AND (%s)"
            % усл, (м,)) if р["inn"]}

    а = месяцы["2026-08"] & set(инн_бит)
    с = месяцы["2026-09"] & set(инн_бит)
    оба = а & с
    print("в Битрикс из августовского охвата:  %d" % len(а))
    print("в Битрикс из сентябрьского охвата:  %d" % len(с))
    print("сумма строк:                        %d" % (len(а) + len(с)))
    print("без двойного счёта:                 %d" % len(а | с))
    print("")
    print("--- те, кто в обоих месяцах (учтены дважды): %d ---" % len(оба))
    for и in sorted(оба):
        лид, имя = инн_бит[и]
        п = c.execute(
            "SELECT substr(m.sent_at,1,10) д, m.mailbox_id FROM messages m "
            "  JOIN recipients r ON m.recipient_id = r.id "
            " WHERE m.status='sent' AND r.inn=? AND (%s) ORDER BY m.sent_at"
            % усл, (и,)).fetchall()
        print("   лид %-5s ИНН %-12s %s" % (лид, и, str(имя)[:34]))
        for с2 in п:
            print("      письмо %s с %s" % (с2["д"], с2["mailbox_id"]))
print("")
print("=" * 74)
print("=== ОТКУДА 21 ВМЕСТО 19 ===")
