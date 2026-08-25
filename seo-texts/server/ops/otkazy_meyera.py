# -*- coding: utf-8 -*-
"""Масштаб отказов Яндекса «подозрение на спам» по ящикам и направлениям."""
import sqlite3
from collections import Counter, defaultdict

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row

print("=== ПОЛНЫЕ ПРИЧИНЫ ПАУЗ ===")
for р in c.execute("SELECT mailbox_id, pause_reason FROM mailbox_state "
                   " WHERE paused=1"):
    print("   %-38s %s" % (р["mailbox_id"], р["pause_reason"]))

МЕЙЕР = ("zernosort", "optic-sort", "sort-systems")


def напр(я):
    return "Meyer" if any(д in (я or "") for д in МЕЙЕР) else "КЦ"


print("\n=== ОТПРАВЛЕНО И ОТКАЗАНО ПО ДНЯМ ===")
дни = defaultdict(Counter)
for р in c.execute(
        "SELECT substr(COALESCE(sent_at, updated_at),1,10) д, mailbox_id я, "
        "       status, COALESCE(last_error,'') ош FROM messages "
        " WHERE status IN ('sent','failed') "
        "   AND substr(COALESCE(sent_at, updated_at),1,10) >= '2026-08-20'"):
    н = напр(р["я"])
    if р["status"] == "sent":
        дни[(р["д"], н)]["ушло"] += 1
    elif "suspicion of SPAM" in р["ош"] or "spam" in р["ош"].lower():
        дни[(р["д"], н)]["отказ по спаму"] += 1
    else:
        дни[(р["д"], н)]["прочий срыв"] += 1
for к in sorted(дни):
    ст = дни[к]
    ушло, отказ = ст["ушло"], ст["отказ по спаму"]
    доля = 100.0 * отказ / (ушло + отказ) if (ушло + отказ) else 0.0
    print("   %s %-6s ушло %4d  отказ по спаму %3d (%4.1f%%)  прочих срывов %d"
          % (к[0], к[1], ушло, отказ, доля, ст["прочий срыв"]))

print("\n=== КОМУ ЛЕТЕЛИ ОТКАЗАННЫЕ ПИСЬМА ===")
for р in c.execute(
        "SELECT r.email, m.subject, m.mailbox_id FROM messages m "
        "  JOIN recipients r ON r.id=m.recipient_id "
        " WHERE m.status='failed' AND m.last_error LIKE '%suspicion of SPAM%' "
        " ORDER BY m.updated_at DESC LIMIT 10"):
    дом = str(р["email"] or "").split("@")[-1]
    print("   %-22s <- %-30s %s" % (дом, р["mailbox_id"], str(р["subject"])[:44]))
print("\n   домены получателей у отказов:")
for к, н in Counter(
        str(р[0] or "").split("@")[-1] for р in c.execute(
            "SELECT r.email FROM messages m JOIN recipients r "
            "    ON r.id=m.recipient_id WHERE m.status='failed' "
            "   AND m.last_error LIKE '%suspicion of SPAM%'")).most_common(8):
    print("      %-24s %4d" % (к, н))
