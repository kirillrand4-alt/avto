# -*- coding: utf-8 -*-
"""Поправить причину паузы food-sort.ru: DNS в порядке, дело в объёме."""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

ЯЩИКИ = ("a.erokhin@food-sort.ru", "s.kozlov@food-sort.ru")
ПРИЧИНА = ("домен food-sort.ru: 90 писем за двое суток при кривой прогрева 3+5, "
           "69 из них за один час; 6 жёстких отбивок и 3 спам-отказа. "
           "DNS в порядке (SPF, DKIM mail._domainkey, DMARC p=quarantine, MX yandex "
           "— всё как у прогретых доменов). Причина в объёме, а не в записях. "
           "Снимать с паузы только после прогрева с первого дня рампы.")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
for m in ЯЩИКИ:
    store.set_mailbox_paused(m, True, ПРИЧИНА)

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
print("=== ПРИЧИНА ОБНОВЛЕНА ===")
for m in ЯЩИКИ:
    р = s.execute("SELECT paused, pause_reason FROM mailbox_state WHERE mailbox_id=?",
                  (m,)).fetchone()
    print("  %-24s paused=%s" % (m, р["paused"]))
    print("     %s" % str(р["pause_reason"])[:150])

print("\n=== ИТОГ: письма в статусе sending (держат аренду перед рестартом) ===")
for р in s.execute("SELECT status, COUNT(*) n FROM messages"
                   " WHERE status IN ('sending','scheduled') GROUP BY status"):
    print("  %-12s %d" % (р["status"], р["n"]))
for р in s.execute("SELECT id, mailbox_id, claimed_at FROM messages"
                   " WHERE status='sending' ORDER BY claimed_at LIMIT 12"):
    print("  #%-7s %-34s claimed %s"
          % (р["id"], str(р["mailbox_id"])[:34], str(р["claimed_at"])[:19]))
