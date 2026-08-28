# -*- coding: utf-8 -*-
"""Добор входящих задним числом: перечитать ящики за N дней.

Вотчер берёт только UNSEEN и помечает \\Seen. Письмо, открытое в почтовом
клиенте раньше него, он не увидит никогда — так потерялись ответы «Азия
цемент», «Содружество», «Первый промышленный консорциум» и один отказ
доставки. Читаем режимом SINCE без пометки \\Seen: непрочитанное владельца
не трогаем, от повторов держит dedup_key события (uidvalidity+uid).
"""
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
ДНЕЙ = int(next((a for a in sys.argv[1:] if a.isdigit()), "7"))
from datetime import datetime, timedelta, timezone                # noqa: E402
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.wiring import build_deps                              # noqa: E402

МЕС = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
       7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}
д = datetime.now(timezone.utc) - timedelta(days=ДНЕЙ)
крит = ("SINCE", "%02d-%s-%d" % (д.day, МЕС[д.month], д.year))
print("критерий: %s" % (крит,))

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
# Вотчера в deps нет — собираем той же сборкой, что cli: со стоп-листом,
# лид-деском и генератором черновиков ответа, иначе добор не заведёт ни
# карточек лидов, ни черновиков.
from sender.imap_watcher import ImapWatcher                       # noqa: E402
from sender.suppression import Suppression                        # noqa: E402
w = ImapWatcher(cfg, store, getattr(deps, "suppression", None) or Suppression(store),
                getattr(deps, "leaddesk", None),
                getattr(deps, "reply_pipeline", None))
было = store._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] \
    if hasattr(store, "_conn") else 0
итог = Counter()
t0 = time.time()
for mb in cfg.mailboxes():
    ид = getattr(mb, "mailbox_id", "")
    try:
        ев = w.poll_once(ид, criteria=крит, mark_seen=False)
        итог["событий: " + ид[:34]] = len(ев or [])
    except Exception as ex:                                       # noqa: BLE001
        итог["ОШИБКА " + ид[:30]] = 1
        print("   %s: %s" % (ид, str(ex)[:90]), flush=True)
стало = store._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] \
    if hasattr(store, "_conn") else 0
print("")
print("прошло %.0f с, событий в базе было %d, стало %d (+%d)"
      % (time.time() - t0, было, стало, стало - было))
for к, n in sorted(итог.items()):
    if n:
        print("   %-46s %3d" % (к, n))
