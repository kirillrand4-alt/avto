# -*- coding: utf-8 -*-
"""Август и сентябрь целиком: письма → ответы → карточки → Битрикс.

Всё привязано к МЕСЯЦУ ПИСЬМА, а не к дате события: письмо августа,
по которому сделка завелась в сентябре, — заслуга августа.

«Передали в Битрикс» — заход в статус когда-либо (lead_events), а не
текущий статус: карточку могли потом закрыть, но она там была.
"""
import sys
from collections import Counter

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
    # какие лиды когда-либо были в Битриксе
    в_битриксе = {р["lead_id"] for р in c.execute(
        "SELECT DISTINCT lead_id FROM lead_events WHERE to_status='in_bitrix'")}
    for р in c.execute("SELECT id FROM leads WHERE status='in_bitrix'"):
        в_битриксе.add(р["id"])

    for м in МЕСЯЦЫ:
        писем = c.execute(
            "SELECT COUNT(*) FROM messages m WHERE m.status='sent' "
            "  AND substr(m.sent_at,1,7)=? AND (%s)" % усл, (м,)).fetchone()[0]
        # получатели месяца
        получатели = {р["rid"] for р in c.execute(
            "SELECT DISTINCT m.recipient_id rid FROM messages m "
            " WHERE m.status='sent' AND substr(m.sent_at,1,7)=? AND (%s)"
            % усл, (м,))}
        инн = {str(р["inn"]).strip() for р in c.execute(
            "SELECT DISTINCT r.inn FROM messages m "
            "  JOIN recipients r ON m.recipient_id = r.id "
            " WHERE m.status='sent' AND substr(m.sent_at,1,7)=? AND (%s)"
            % усл, (м,)) if р["inn"]}
        живые = c.execute(
            "SELECT COUNT(*) FROM events e JOIN messages m ON e.message_id = m.id "
            " WHERE e.event_type='reply' AND m.status='sent' "
            "   AND substr(m.sent_at,1,7)=? AND (%s)" % усл, (м,)).fetchone()[0]
        # карточки лидов этих компаний
        лиды, биты = set(), set()
        for л in c.execute("SELECT id, inn, recipient_id FROM leads"):
            свой = (str(л["inn"] or "").strip() in инн) or (л["recipient_id"] in получатели)
            if not свой:
                continue
            лиды.add(л["id"])
            if л["id"] in в_битриксе:
                биты.add(л["id"])
        строки.append((м, писем, живые, len(лиды), len(биты)))

print("   %-10s %8s %8s %8s %10s %9s"
      % ("месяц", "писем", "ответов", "карточек", "в Битрикс", "доля"))
for м, п, ж, л, б in строки:
    print("   %-10s %8d %8d %8d %10d %8.2f%%"
          % (м, п, ж, л, б, 100.0 * б / п if п else 0))
print("")
print("=" * 74)
print("=== ВОРОНКА MEYER ПО МЕСЯЦАМ ===")
for м, п, ж, л, б in строки:
    print("   %s: из %d писем → %d ответов → %d карточек → %d в Битрикс"
          % (м, п, ж, л, б))
