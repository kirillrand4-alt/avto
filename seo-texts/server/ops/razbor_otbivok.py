# -*- coding: utf-8 -*-
"""Отбивки за сегодня: сколько, почему, и была ли проба адреса ДО отправки."""
import re, sys
from collections import Counter
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
    кол = [c[1] for c in store._conn.execute("PRAGMA table_info(events)")]
    вр = next((c for c in ("ts", "created_at") if c in кол), None)
    тп = next((c for c in ("type", "event_type") if c in кол), None)
    пч = next((c for c in ("email", "recipient_email") if c in кол), None)
    мид = next((c for c in ("message_id", "msg_id") if c in кол), None)
    ушло = store._conn.execute(
        "SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at >= "
        "datetime('now','start of day')").fetchone()[0]
    события = Counter()
    for р in store._conn.execute(
            "SELECT %s t, COUNT(*) c FROM events WHERE %s >= "
            "datetime('now','start of day') GROUP BY %s" % (тп, вр, тп)):
        события[str(р["t"])] = int(р["c"])
    отбивки = store._conn.execute(
        "SELECT * FROM events WHERE %s IN ('bounce','reject_spam') AND %s >= "
        "datetime('now','start of day') ORDER BY %s" % (тп, вр, вр)).fetchall()
    пробы = {}
    for р in store._conn.execute("SELECT email, verdict, ts FROM addr_probe"):
        пробы[str(р["email"] or "").lower()] = (str(р["verdict"] or ""),
                                                разбор(р["ts"]))
    # сколько сегодняшних отправок вообще имели пробу до отправки
    было_пробы = Counter()
    for р in store._conn.execute(
            "SELECT m.sent_at, r.email FROM messages m "
            "  LEFT JOIN recipients r ON m.recipient_id = r.id "
            " WHERE m.status='sent' AND m.sent_at >= datetime('now','start of day')"):
        а = str(р["email"] or "").lower()
        п = пробы.get(а)
        s = разбор(р["sent_at"])
        if not п:
            было_пробы["пробы не было вовсе"] += 1
        elif п[1] and s and п[1] <= s:
            было_пробы["проба была ДО отправки: " + (п[0] or "?")] += 1
        else:
            было_пробы["проба ПОСЛЕ отправки: " + (п[0] or "?")] += 1

# АДРЕС ПОЛУЧАТЕЛЯ БЕРЁМ ЧЕРЕЗ ПИСЬМО, А НЕ РЕГУЛЯРКОЙ ПО ТЕКСТУ СОБЫТИЯ.
# В тексте отбивки стоит НАШ ящик («dsn bounce y.kuzmin@optic-sort.ru»), и
# первый заход посчитал пробу по нему - то есть не нашёл ни одной.
адрес_письма = {}
with store._lock:
    for р in store._conn.execute(
            "SELECT m.id, r.email FROM messages m "
            "  LEFT JOIN recipients r ON m.recipient_id = r.id "
            " WHERE m.updated_at >= datetime('now','-2 days')"):
        адрес_письма[int(р["id"])] = str(р["email"] or "").lower()

причины = Counter()
без_пробы = []
for р in отбивки:
    текст = " ".join(str(р[c] or "") for c in кол if isinstance(р[c], str))
    а = ""
    if мид and р[мид]:
        а = адрес_письма.get(int(р[мид]), "")
    if not а and пч:
        а = str(р[пч] or "").lower()
    п = пробы.get(а)
    вр_соб = разбор(р[вр])
    было = "нет" if not п else ("до" if (п[1] and вр_соб and п[1] <= вр_соб)
                                else "после")
    причины["%s | проба %s | %s" % (str(р[тп]), было, (п[0] if п else "-"))] += 1
    if было == "нет":
        без_пробы.append((а, str(р[тп]), текст[:90]))

print("--- отбивки без предварительной пробы (до 12) ---")
for а, т, х in без_пробы[:12]:
    print("   %-34s %-12s %s" % (а[:34], т, х[:70]))
print("")
print("--- проверка адресов у сегодняшних отправок ---")
for к, в in было_пробы.most_common(8):
    print("   %-44s %5d" % (к, в))
print("")
print("=" * 74)
print("=== ОТБИВКИ ЗА СЕГОДНЯ ===")
print("отправлено сегодня: %d" % ушло)
for к, в in события.most_common(8):
    print("   событие %-20s %5d" % (к, в))
print("")
for к, в in причины.most_common(10):
    print("   %-54s %4d" % (к, в))
