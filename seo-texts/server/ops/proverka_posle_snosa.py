# -*- coding: utf-8 -*-
"""Что стало с конфигом после сноса компрессорных ящиков."""
import io
import re
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

ФАЙЛ = r"C:\sender\sender.yaml"
т = io.open(ФАЙЛ, encoding="utf-8").read()
cfg = Config.load(ФАЙЛ)
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

print("--- раздел provider_split целиком ---")
вкл = False
for с in т.splitlines():
    if с.startswith("provider_split:"):
        вкл = True
    elif вкл and re.match(r"^[^\s#]", с):
        break
    if вкл:
        print("   " + с[:150])

print("")
print("--- ящики конфига (%d) ---" % len(cfg.mailboxes()))
for m in cfg.mailboxes():
    print("   %-38s провайдер=%s" % (m.mailbox_id, getattr(m, "provider", "?")))

print("")
print("--- кампании, которым конфиг прописал пул ---")
with store._lock:
    for р in store._conn.execute(
            "SELECT id, name, provider_pool FROM campaigns "
            " WHERE provider_pool IS NOT NULL AND provider_pool<>'' ORDER BY id"):
        плохо = "   ПУЛА БОЛЬШЕ НЕТ" if р["provider_pool"] not in (
            cfg.provider_pools() or {}) else ""
        print("   кампания %-4s %-30s пул=%s%s"
              % (р["id"], str(р["name"])[:30], р["provider_pool"], плохо))

print("")
print("--- упоминания pool_mailru где-либо в конфиге ---")
n = sum(1 for с in т.splitlines() if "pool_mailru" in с)
print("   строк: %d" % n)
print("")
print("=" * 74)
print("=== ПРОВЕРКА ПОСЛЕ СНОСА ===")
