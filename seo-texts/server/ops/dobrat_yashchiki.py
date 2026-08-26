# -*- coding: utf-8 -*-
"""Разобрать письма, которые лежат в ящиках, но в базу не попали.

Сверка ящиков нашла три: ответ «ПК Контур» от 25.08, ответ
«Промкомплектация» от 26.08 и DMARC-отчёт. Первые два — настоящие ответы
на наши письма, и в ленте лидов их нет.

Гоняем ШТАТНЫЙ разбор (ImapWatcher.poll_once) с критерием SINCE: он сам
заведёт события, карточку лида и черновик ответа. Флаг \\Seen не ставим —
владелец читает ящики руками.

    python dobrat_yashchiki.py            # показать письма
    python dobrat_yashchiki.py primenit   # разобрать
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402
from sender.mailbrowser import MailBrowser    # noqa: E402

ДЕЛАТЬ = "primenit" in sys.argv[1:]
ЯЩИКИ = ("a.balakirev@compressor-air-expert.ru",
         "k.yashin@kompressor-expert.ru",
         "a.balakirev@compressor-store.ru")
С_КОГДА = "24-Aug-2026"

cfg = Config.load(r"C:\sender\sender.yaml")
mb = MailBrowser(cfg)

print("=== письма в ящиках ===")
for яид in ЯЩИКИ:
    try:
        д = mb.messages(яид, folder="INBOX", limit=40)
    except Exception as ex:                                   # noqa: BLE001
        print("%s: не открылся (%s)" % (яид, str(ex)[:60]))
        continue
    for п in (д.get("messages") or []):
        отпр = str(п.get("from_addr") or "")
        if "kompressor" in отпр or "compressor-store" in отпр or "optic-sort" in отпр:
            continue
        if str(п.get("date_iso") or "") < "2026-08-24":
            continue
        print("   %-42s %s | %s" % (яид[:42], str(п.get("date_iso"))[:16], отпр))
        print("      %s" % str(п.get("subject"))[:90])

if not ДЕЛАТЬ:
    print("\nвхолостую. Разобрать — primenit")
    raise SystemExit(0)

from sender.imap_watcher import ImapWatcher   # noqa: E402
from sender.leaddesk import LeadDesk          # noqa: E402
from sender.store import Store                # noqa: E402
from sender.suppression import Suppression    # noqa: E402

store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
сторож = ImapWatcher(cfg, store, Suppression(store),
                     reply_desk=LeadDesk(cfg, store))
for яид in ЯЩИКИ:
    try:
        события = сторож.poll_once(яид, criteria=("SINCE", С_КОГДА),
                                   mark_seen=False)
    except Exception as ex:                                   # noqa: BLE001
        print("%s: разбор упал — %s" % (яид, str(ex)[:120]))
        continue
    виды = {}
    for e in события:
        виды[e.kind] = виды.get(e.kind, 0) + 1
    print("%-42s разобрано %d: %s" % (яид[:42], len(события), виды or "—"))
