# -*- coding: utf-8 -*-
"""Письма, ушедшие на адреса с УЖЕ ИЗВЕСТНЫМ приговором «нет ящика»."""
import sys
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402


def разбор(т):
    т = str(т or "").strip().replace("T", " ").split("+")[0].split(".")[0]
    for ф in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(т, ф).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


store = Store(r"C:\sender\sender.db")
with store._lock:
    пробы = {str(р["email"] or "").lower(): (str(р["verdict"] or ""),
                                             разбор(р["ts"]), str(р["answer"] or ""))
             for р in store._conn.execute(
                 "SELECT email, verdict, ts, answer FROM addr_probe")}
    письма = store._conn.execute(
        "SELECT m.id, m.sent_at, m.subject, r.email, r.inn "
        "  FROM messages m LEFT JOIN recipients r ON m.recipient_id = r.id "
        " WHERE m.status='sent' AND m.sent_at >= datetime('now','start of day')"
    ).fetchall()

плохие = []
for р in письма:
    а = str(р["email"] or "").lower()
    п = пробы.get(а)
    if not п:
        continue
    вердикт, ts, ответ = п
    s = разбор(р["sent_at"])
    if вердикт in ("нет ящика", "нет MX") and ts and s and ts <= s:
        плохие.append((а, вердикт, ts, s, (s - ts).total_seconds() / 3600.0,
                       ответ, р["id"]))
плохие.sort(key=lambda x: -x[4])
for а, в, ts, s, ч, ответ, mid in плохие[:20]:
    print("   %-32s %-10s приговор %s → отправка %s (через %.1f ч)"
          % (а[:32], в, ts.strftime("%m-%d %H:%M"), s.strftime("%m-%d %H:%M"), ч))
print("")
print("=" * 78)
print("=== ПИСЬМА НА АДРЕСА С ГОТОВЫМ ПРИГОВОРОМ ===")
print("отправлено сегодня: %d; из них на заведомо мёртвые: %d"
      % (len(письма), len(плохие)))
if плохие:
    зазор = sorted(x[4] for x in плохие)
    print("зазор приговор→отправка: от %.1f до %.1f часов, медиана %.1f"
          % (зазор[0], зазор[-1], зазор[len(зазор) // 2]))
