# -*- coding: utf-8 -*-
"""След ответа Медведовского: события письма, ссылки лидов, соседние лиды 04.09."""
import sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

ПИСЬМО = 14957
ПОЧТА = "krimck1600@mail.ru"
store = Store(r"C:\sender\sender.db")
with store._lock:
    кол = [c[1] for c in store._conn.execute("PRAGMA table_info(events)")]
    мид = next((c for c in ("message_id",) if c in кол), None)
    print("--- события письма %s ---" % ПИСЬМО)
    for р in store._conn.execute(
            "SELECT * FROM events WHERE %s=?" % мид, (ПИСЬМО,)):
        print("   " + " | ".join("%s=%s" % (k, str(р[k])[:60])
                                 for k in кол if р[k] not in (None, "")))
    m = store._conn.execute(
        "SELECT id, thread_id, rfc_message_id, status, sent_at, mailbox_id "
        "  FROM messages WHERE id=?", (ПИСЬМО,)).fetchone()
    print("")
    print("--- само письмо ---")
    if m:
        for k in ("id", "thread_id", "rfc_message_id", "status", "sent_at",
                  "mailbox_id"):
            print("   %-16s %s" % (k, m[k]))
    print("")
    print("--- лиды, заведённые 04.09 ---")
    for р in store._conn.execute(
            "SELECT id, email, company_name, status, reply_kind, created_at, "
            "       thread_id FROM leads WHERE substr(created_at,1,10)='2026-09-04'"
            " ORDER BY id"):
        print("   лид %-5s %-30s %-26s %-12s %s"
              % (р["id"], str(р["email"])[:30], str(р["company_name"])[:26],
                 str(р["reply_kind"]), str(р["created_at"])[11:16]))
    print("")
    print("--- есть ли лид с этим thread_id ---")
    if m and m["thread_id"]:
        for р in store._conn.execute(
                "SELECT id, email, company_name, status FROM leads WHERE thread_id=?",
                (m["thread_id"],)):
            print("   лид %s %s %s %s" % (р["id"], р["email"], р["company_name"],
                                          р["status"]))
    print("")
    print("--- lead_ssylki по адресу ---")
    try:
        кс = [c[1] for c in store._conn.execute("PRAGMA table_info(lead_ssylki)")]
        for р in store._conn.execute(
                "SELECT * FROM lead_ssylki WHERE %s"
                % " OR ".join("%s LIKE ?" % c for c in кс if c.endswith(("email", "id"))),
                tuple("%" + ПОЧТА + "%" for c in кс if c.endswith(("email", "id")))):
            print("   " + " | ".join("%s=%s" % (k, str(р[k])[:50]) for k in кс))
    except Exception as ex:                                     # noqa: BLE001
        print("   не прочиталось: %s" % str(ex)[:80])
print("")
print("=" * 74)
print("=== СЛЕД ОТВЕТА МЕДВЕДОВСКОГО ===")
