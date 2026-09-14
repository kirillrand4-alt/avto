# -*- coding: utf-8 -*-
"""Доскрёб входящих: разобрать письма, которые штатный опрос не увидел.

Штатный сборщик берёт ТОЛЬКО UNSEEN. Если письмо кто-то прочитал руками в
веб-почте раньше, чем подошёл тик, оно исчезает из выборки навсегда: ни
события, ни лида. Так пропал горячий ответ Медведовского ЗПП от 04.09
(«Пришлите предложение по оборудованию») — лежит в INBOX прочитанным,
uid 32, а в журнале ящика есть uid 31 и uid 33 и нет 32.

Здесь тот же ImapWatcher, но критерий SINCE и БЕЗ пометки \\Seen: чужое
непрочитанное не трогаем, от повторов защищает дедуп (ключ ящик+uid и
второй заслон по Message-ID письма). Черновики ответов не готовим.

argv: [дата SINCE как 01-Sep-2026] [ящик или 'все'] [потолок писем на ящик]
"""
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.imap_watcher import ImapWatcher                     # noqa: E402
from sender.wiring import build_deps                            # noqa: E402

СИНС = sys.argv[1] if len(sys.argv) > 1 else "01-Sep-2026"
ЯЩИК = sys.argv[2] if len(sys.argv) > 2 else "i.boyarkin@zernosort.ru"
ПОТОЛОК = int(sys.argv[3]) if len(sys.argv) > 3 else 200

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
watcher = ImapWatcher(cfg, store, deps.suppression, deps.leaddesk,
                      reply_pipeline=None)

все_ящики = [m.mailbox_id for m in cfg.mailboxes()]
if ЯЩИК == "все":
    ящики = все_ящики
elif ЯЩИК.startswith(("часть:", "part:")):
    # «часть:0:12» — срез списка ящиков, чтобы уложиться в потолок задания
    _, а, б = ЯЩИК.split(":")
    ящики = все_ящики[int(а):int(б)]
else:
    ящики = [ЯЩИК]
print("ящиков в работе: %d из %d" % (len(ящики), len(все_ящики)))


def замер():
    with store._lock:
        с = store._conn
        е = с.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        л = с.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    return int(е), int(л)


было_е, было_л = замер()
строки = []
итог = Counter()
беда = []
начало = time.time()
for мид in ящики:
    if time.time() - начало > 700:
        строки.append("   ... время вышло, остальные ящики не трогали")
        break
    try:
        события = watcher.poll_once(мид, criteria=("SINCE", СИНС),
                                    batch=ПОТОЛОК, mark_seen=False)
    except Exception as ex:                                     # noqa: BLE001
        беда.append("%s: %s" % (мид, str(ex)[:90]))
        continue
    виды = Counter(е.kind for е in события)
    for к, в in виды.items():
        итог[к] += в
    строки.append("   %-44s %s"
                  % (мид[:44], ", ".join("%s=%d" % (к, в)
                                         for к, в in sorted(виды.items()))
                     or "пусто"))

стало_е, стало_л = замер()

# что нового завелось в лидах
новые = []
with store._lock:
    for р in store._conn.execute(
            "SELECT id, email, company_name, status, created_at FROM leads "
            " ORDER BY id DESC LIMIT ?", (max(0, стало_л - было_л) or 0,)):
        новые.append("   лид %-6s %-28s %-30s %s"
                     % (р["id"], str(р["email"])[:28],
                        str(р["company_name"])[:30], str(р["created_at"])[:19]))

print("--- по ящикам ---")
print("\n".join(строки))
if беда:
    print("")
    print("--- ящики, куда не вошли (%d) ---" % len(беда))
    for с in беда:
        print("   " + с)
if новые:
    print("")
    print("--- новые карточки лидов ---")
    print("\n".join(новые))
print("")
print("=" * 74)
print("=== ДОСКРЁБ ВХОДЯЩИХ С %s ===" % СИНС)
print("   писем разобрано: %s"
      % (", ".join("%s=%d" % (к, в) for к, в in sorted(итог.items())) or "нет"))
print("   событий в базе:  %d → %d  (+%d)" % (было_е, стало_е, стало_е - было_е))
print("   лидов в базе:    %d → %d  (+%d)" % (было_л, стало_л, стало_л - было_л))
