# -*- coding: utf-8 -*-
"""Пулы ящиков и очередь по кампаниям: что осиротеет без компрессорных."""
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
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
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

print("--- пулы ---")
for имя, состав in (cfg.provider_pools() or {}).items():
    живых = [x for x in состав if x not in МЁРТВЫЕ]
    print("   %-24s всего %2d, живых %2d%s"
          % (имя, len(состав), len(живых),
             "   <-- ПУЛ ОПУСТЕЕТ" if not живых else ""))
    for x in состав:
        print("       %-44s %s" % (x, "МЁРТВ" if x in МЁРТВЫЕ else ""))

print("")
print("--- кампании и что у них в очереди ---")
with store._lock:
    c = store._conn
    кол = [x[1] for x in c.execute("PRAGMA table_info(campaigns)")]
    имя_к = next((x for x in ("name", "title", "campaign_name") if x in кол), None)
    напр = next((x for x in ("division", "napravlenie", "brand", "pool")
                 if x in кол), None)
    for р in c.execute("SELECT * FROM campaigns ORDER BY id"):
        в_работе = c.execute(
            "SELECT COUNT(*) FROM messages WHERE campaign_id=? "
            "  AND status NOT IN ('sent','skipped','failed')",
            (р["id"],)).fetchone()[0]
        ушло = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=? "
                         "  AND status='sent'", (р["id"],)).fetchone()[0]
        if not в_работе and not ушло:
            continue
        print("   кампания %-4s %-34s %-12s в работе %4d, ушло %5d"
              % (р["id"], str(р[имя_к] if имя_к else "")[:34],
                 str(р[напр] if напр else "")[:12], в_работе, ушло))
print("")
print("   колонки campaigns: %s" % ", ".join(кол))
print("")
print("=" * 74)
print("=== ПУЛЫ И КАМПАНИИ ===")
