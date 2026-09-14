# -*- coding: utf-8 -*-
"""Письма в очереди, которым больше не с чего уходить.

Компрессорных ящиков не осталось. Смотрим, какие кампании очереди
компрессорные (по тому, с каких ящиков у них уходили письма раньше),
сколько таких писем висит и видит ли их оператор в очереди подтверждения.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

МЁРТВЫЕ = {
    "v.melnikov@kompressor-air-trade.ru", "i.lyapin@kompressor-air-trade.ru",
    "k.yashin@kompressor-pro-expert.ru", "o.tseyzer@kompressor-pro-expert.ru",
    "a.balakirev@compressor-air-expert.ru", "v.prokhorov@compressor-air-expert.ru",
    "p.novoseltsev@kompressor-pro-trade.ru", "m.pavlov@kompressor-pro-trade.ru",
    "v.melnikov@kompressor-air-expert.ru", "i.lyapin@kompressor-air-expert.ru",
    "k.yashin@kompressor-expert.ru", "o.tseyzer@kompressor-expert.ru",
    "a.balakirev@compressor-store.ru", "l.abubakirov@compressor-store.ru",
}
store = Store(r"C:\sender\sender.db")
всего_кц = 0
with store._lock:
    c = store._conn
    print("--- кампании с письмами в работе ---")
    for р in c.execute(
            "SELECT m.campaign_id к, COUNT(*) n FROM messages m "
            " WHERE m.status NOT IN ('sent','skipped','failed') "
            " GROUP BY 1 ORDER BY 1"):
        к, n = р["к"], int(р["n"])
        имя = c.execute("SELECT name FROM campaigns WHERE id=?", (к,)).fetchone()
        ящики = Counter()
        for р2 in c.execute(
                "SELECT mailbox_id, COUNT(*) n FROM messages "
                " WHERE campaign_id=? AND status='sent' AND mailbox_id IS NOT NULL"
                " GROUP BY 1 ORDER BY 2 DESC LIMIT 6", (к,)):
            ящики[р2["mailbox_id"]] = int(р2["n"])
        мертво = sum(в for я, в in ящики.items() if я in МЁРТВЫЕ)
        живо = sum(в for я, в in ящики.items() if я not in МЁРТВЫЕ)
        направление = ("КОМПРЕССОРНАЯ — отправлять НЕ С ЧЕГО"
                       if мертво and not живо else
                       ("смешанная" if мертво else "Meyer — уходит"))
        if мертво and not живо:
            всего_кц += n
        print("   кампания %-4s %-32s в работе %4d   %s"
              % (к, str(имя["name"] if имя else "")[:32], n, направление))
        for я, в in ящики.most_common(3):
            print("       раньше уходило с %-42s %5d%s"
                  % (я[:42], в, "  МЁРТВ" if я in МЁРТВЫЕ else ""))

    print("")
    print("--- сколько из них ждёт оператора в очереди подтверждения ---")
    for р in c.execute(
            "SELECT status, COUNT(*) n FROM confirm_reviews GROUP BY 1"):
        print("   %-18s %5d" % (р["status"], р["n"]))
print("")
print("=" * 74)
print("=== ОСИРОТЕВШИЕ ПИСЬМА ===")
print("   писем компрессорных кампаний в работе: %d" % всего_кц)
