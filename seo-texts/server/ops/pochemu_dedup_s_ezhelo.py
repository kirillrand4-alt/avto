# -*- coding: utf-8 -*-
"""Доскрёб разобрал 24 письма и не завёл ни одного события. Смотрим почему.

Перехватываем append_event: печатаем ключ дедупа, Message-ID письма, тему,
отправителя и вердикт (создано/съедено). Ничего не ломаем — настоящий
append_event вызывается как был.
"""
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.imap_watcher import ImapWatcher                     # noqa: E402
from sender.wiring import build_deps                            # noqa: E402

ЯЩИК = sys.argv[1] if len(sys.argv) > 1 else "i.boyarkin@zernosort.ru"
СИНС = sys.argv[2] if len(sys.argv) > 2 else "03-Sep-2026"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)

журнал = []
родной = store.append_event


def подглядеть(e):
    ид, создано = родной(e)
    шапка = (e.detail or {}).get("headers") or {}
    журнал.append((e.dedup_key, str(шапка.get("Message-ID") or "")[:60],
                   str(шапка.get("From") or "")[:46],
                   str(шапка.get("Subject") or "")[:40],
                   e.event_type, ид, создано))
    return ид, создано


store.append_event = подглядеть
watcher = ImapWatcher(cfg, store, deps.suppression, deps.leaddesk,
                      reply_pipeline=None)
события = watcher.poll_once(ЯЩИК, criteria=("SINCE", СИНС), batch=200,
                            mark_seen=False)
store.append_event = родной

print("--- что предлагали записать ---")
for ключ, мид, отк, тема, тип, ид, создано in журнал:
    print("   %-28s %-10s событие=%-7s %s"
          % (ключ, "СОЗДАНО" if создано else "СЪЕДЕНО", ид, тип))
    print("       от %-46s %s" % (отк, тема))
    print("       msgid %s" % мид)

# кто именно съел: ищем событие с тем же rfc_msgid
with store._lock:
    print("")
    print("--- кем съедено (строка-двойник в базе) ---")
    for ключ, мид, отк, тема, тип, ид, создано in журнал:
        if создано:
            continue
        р = store._conn.execute(
            "SELECT id, dedup_key, event_type, event_ts, mailbox_id, rfc_msgid "
            "  FROM events WHERE id=?", (ид,)).fetchone()
        if р:
            print("   %-28s → #%-7s %-12s %s ключ=%s"
                  % (ключ, р["id"], р["event_type"], str(р["event_ts"])[:19],
                     str(р["dedup_key"])[:30]))
            print("       rfc_msgid двойника: %s" % str(р["rfc_msgid"])[:70])
        else:
            print("   %-28s → строки #%s в базе НЕТ (событие не легло вовсе)"
                  % (ключ, ид))
print("")
print("=" * 74)
print("=== ПОЧЕМУ ДОСКРЁБ НИЧЕГО НЕ ЗАВЁЛ (%s, %d писем) ==="
      % (ЯЩИК, len(журнал)))
