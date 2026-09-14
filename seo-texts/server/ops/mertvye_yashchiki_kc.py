# -*- coding: utf-8 -*-
"""За что ещё держатся ящики удалённых компрессорных доменов.

Владелец удалил компрессорные домены совсем. Смотрим, где они ещё
прописаны: конфиг, пулы, письма в очереди, отправки, паузы, — и что
сломается, если их убрать.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

МЁРТВЫЕ = [
    "v.melnikov@kompressor-air-trade.ru", "i.lyapin@kompressor-air-trade.ru",
    "k.yashin@kompressor-pro-expert.ru", "o.tseyzer@kompressor-pro-expert.ru",
    "a.balakirev@compressor-air-expert.ru", "v.prokhorov@compressor-air-expert.ru",
    "p.novoseltsev@kompressor-pro-trade.ru", "m.pavlov@kompressor-pro-trade.ru",
    "v.melnikov@kompressor-air-expert.ru", "i.lyapin@kompressor-air-expert.ru",
    "k.yashin@kompressor-expert.ru", "o.tseyzer@kompressor-expert.ru",
    "a.balakirev@compressor-store.ru", "l.abubakirov@compressor-store.ru",
]
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

вых = []
ящики = cfg.mailboxes()
вых.append("ящиков в конфиге: %d" % len(ящики))
вых.append("")
вых.append("--- все ящики конфига ---")
for m in ящики:
    метка = "  МЁРТВ" if m.mailbox_id in МЁРТВЫЕ else ""
    вых.append("   %-44s провайдер=%-10s%s"
               % (m.mailbox_id, getattr(m, "provider", "?"), метка))

вых.append("")
вых.append("--- пулы ---")
for имя, состав in (cfg.provider_pools() or {}).items():
    живых = [x for x in состав if x not in МЁРТВЫЕ]
    вых.append("   %-22s всего %2d, живых %2d%s"
               % (имя, len(состав), len(живых),
                  "   ← ПУЛ ОПУСТЕЕТ" if not живых else ""))

with store._lock:
    c = store._conn
    вых.append("")
    вых.append("--- письма, которые уже уходили с этих ящиков ---")
    n = 0
    for р in c.execute(
            "SELECT mailbox_id, COUNT(*) n, MAX(sent_at) п FROM messages "
            " WHERE status='sent' AND mailbox_id IN (%s) GROUP BY 1"
            % ",".join("?" * len(МЁРТВЫЕ)), МЁРТВЫЕ):
        n += 1
        вых.append("   %-44s %5d  последнее %s"
                   % (р["mailbox_id"], р["n"], str(р["п"])[:16]))
    if not n:
        вых.append("   ни одного")

    вых.append("")
    вых.append("--- очередь: письма в работе по направлениям ---")
    for р in c.execute(
            "SELECT campaign_id, status, COUNT(*) n FROM messages "
            " WHERE status NOT IN ('sent','skipped','failed') "
            " GROUP BY 1,2 ORDER BY 1,2"):
        вых.append("   кампания %-4s %-16s %5d"
                   % (р["campaign_id"], р["status"], р["n"]))

    вых.append("")
    вых.append("--- есть ли письма в очереди, привязанные к мёртвым ящикам ---")
    р = c.execute(
        "SELECT COUNT(*) n FROM messages WHERE mailbox_id IN (%s) "
        "  AND status NOT IN ('sent','skipped','failed')"
        % ",".join("?" * len(МЁРТВЫЕ)), МЁРТВЫЕ).fetchone()
    вых.append("   привязано писем: %d" % int(р["n"]))

    вых.append("")
    вых.append("--- состояние ящиков в базе (паузы/лимиты) ---")
    имена = [x[1] for x in c.execute("PRAGMA table_info(mailbox_state)")]
    if имена:
        for р in c.execute("SELECT * FROM mailbox_state ORDER BY mailbox_id"):
            жив = "" if р["mailbox_id"] not in МЁРТВЫЕ else "  МЁРТВ"
            куски = []
            for к in имена:
                if к == "mailbox_id" or р[к] in (None, "", 0):
                    continue
                куски.append("%s=%s" % (к, str(р[к])[:36]))
            вых.append("   %-44s %s%s"
                       % (р["mailbox_id"], "; ".join(куски)[:90], жив))

print("\n".join(вых))
print("")
print("=" * 74)
print("=== ЧЕМ ДЕРЖАТСЯ МЁРТВЫЕ КОМПРЕССОРНЫЕ ЯЩИКИ ===")
