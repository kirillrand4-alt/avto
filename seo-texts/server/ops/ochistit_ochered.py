# -*- coding: utf-8 -*-
"""Очистить очередь подтверждения перед новой партией.

Владелец 12.10: «выкинь из очереди те которые там сейчас стоят, что бы я
чисто новую партию отслеживал».

Выкидываем через штатное решение `skipped` — строки остаются в
confirm_reviews с причиной и автором, письма уходят в messages.skipped.
Ничего не удаляем: очередь можно будет разобрать задним числом.

ОТВЕТЫ КЛИЕНТАМ (kind='reply') НЕ ТРОГАЕМ без отдельной команды: это
написанные ответы живым людям, а не холодные письма партии.

Запуск: ochistit_ochered.py [--primenit] [--i-otvety]
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

ПРИМЕНИТЬ = "--primenit" in sys.argv
И_ОТВЕТЫ = "--i-otvety" in sys.argv
ПРИЧИНА = "очистка очереди перед партией 9000 (команда владельца 12.10)"

store = Store(r"C:\sender\sender.db")
with store._lock:
    строки = [dict(р) for р in store._conn.execute(
        "SELECT id, kind, campaign_id, email, subject, created_at "
        "  FROM confirm_reviews WHERE status='pending' ORDER BY id")]
print("в очереди (pending): %d" % len(строки))

по_виду = Counter(str(р["kind"] or "outbound") for р in строки)
по_кампании = Counter(str(р["campaign_id"]) for р in строки)
for в, n in по_виду.most_common():
    print("   вид %-12s %5d" % (в, n))
print("   кампаний в очереди: %d" % len(по_кампании))
for к, n in по_кампании.most_common(6):
    print("      кампания %-6s %5d" % (к, n))

print("")
print("--- первые письма очереди ---")
for р in строки[:6]:
    print("   #%-6s %-10s %-32s %s"
          % (р["id"], р["kind"], str(р["email"])[:32], str(р["subject"])[:40]))

к_снятию = [р for р in строки
            if И_ОТВЕТЫ or str(р["kind"] or "outbound") != "reply"]
ответов = len(строки) - len(к_снятию)
снято = сбой = 0
if ПРИМЕНИТЬ:
    for р in к_снятию:
        try:
            if store.confirm_decide(р["id"], status="skipped",
                                    reason=ПРИЧИНА, decided_by="claude-ops"):
                снято += 1
            else:
                сбой += 1
        except Exception as e:  # noqa: BLE001
            сбой += 1
            if сбой < 4:
                print("   не снялось #%s: %s" % (р["id"], str(e)[:70]))

with store._lock:
    осталось = store._conn.execute(
        "SELECT COUNT(*) FROM confirm_reviews WHERE status='pending'"
    ).fetchone()[0]

print("")
print("=" * 70)
print("=== ОЧИСТКА ОЧЕРЕДИ ===")
print("   режим:                 %s" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "сухой прогон"))
print("   было в очереди:        %5d" % len(строки))
print("   к снятию:              %5d" % len(к_снятию))
print("   ответов клиентам не трогаем: %d" % ответов)
print("   снято:                 %5d" % снято)
print("   не снялось:            %5d" % сбой)
print("   осталось в очереди:    %5d" % осталось)
