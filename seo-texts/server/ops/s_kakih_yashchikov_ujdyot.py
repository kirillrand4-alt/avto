# -*- coding: utf-8 -*-
"""С каких ящиков реально уйдёт партия: что записано и как выберется.

Ящик выбирается НЕ при постановке в очередь, а на отправке: pick_mailbox
берёт пул по провайдеру получателя, отсекает непригодные по направлению и
лимитам, потом идёт по кругу от последнего использованного. Значит вопрос
«будут ли почты разные» распадается на три: что записано в письмах сейчас,
сколько ящиков Meyer вообще пригодны, и как получатели партии разложены по
провайдерам.
"""
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

ТЕМА = "Для качества: вопрос по сортировке зерна"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

# 1. что записано в письмах партии
ящики = Counter()
провайдеры = Counter()
with store._lock:
    for р in store._conn.execute(
            """SELECT m.mailbox_id, r.domain, r.extra_json
                 FROM confirm_reviews c
                 JOIN messages m ON c.message_id = m.id
                 LEFT JOIN recipients r ON c.recipient_id = r.id
                WHERE c.subject=? AND c.status='pending'""", (ТЕМА,)):
        ящики[str(р["mailbox_id"] or "НЕ ЗАДАН")] += 1
        провайдеры[str(р["domain"] or "?").lower()] += 1

# 2. какие ящики есть и какие из них Meyer
все_ящики = []
try:
    for м in (cfg.get("mailboxes", None) or []):
        все_ящики.append((str((м or {}).get("id") or ""),
                          str((м or {}).get("from_name") or ""),
                          str((м or {}).get("division") or ""),
                          bool((м or {}).get("enabled", True))))
except Exception as ex:                                         # noqa: BLE001
    print("конфиг ящиков не прочитан: %s" % str(ex)[:100])

пулы = {}
try:
    пулы = dict(cfg.provider_pools() or {})
except Exception as ex:                                         # noqa: BLE001
    print("пулы не прочитаны: %s" % str(ex)[:100])

print("--- ящики в конфиге ---")
for i, имя, напр, вкл in все_ящики:
    print("   %-26s %-24s напр=%-6s %s"
          % (i[:26], имя[:24], напр or "?", "вкл" if вкл else "ВЫКЛ"))
print("")
print("--- пулы провайдеров ---")
for имя, сп in пулы.items():
    print("   %-14s %d: %s" % (имя, len(сп), ", ".join(str(x)[:22] for x in сп)))
print("")
print("--- домены получателей партии (топ-10) ---")
for к, в in провайдеры.most_common(10):
    print("   %-26s %5d" % (к, в))
print("")
print("=" * 74)
print("=== ЯЩИК ОТПРАВИТЕЛЯ В ПИСЬМАХ ПАРТИИ ===")
for к, в in ящики.most_common():
    print("   %-30s %5d" % (к, в))
print("ящиков в конфиге: %d; из них Meyer: %d"
      % (len(все_ящики), sum(1 for _i, _n, d, _e in все_ящики
                             if "meyer" in d.lower())))
