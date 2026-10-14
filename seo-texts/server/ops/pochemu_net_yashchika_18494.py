# -*- coding: utf-8 -*-
"""Почему у карточки не подбирается ящик: pochemu_net_yashchika_18494.py <review_id>
Разбор ровно по шагам send_as/_fallback_mailbox: направление письма, разрешённые
направления компании, заслон сделки и состояние каждого ящика (гейт, пауза, лимит)."""
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.store import Store                                      # noqa: E402
from sender.wiring import build_deps                                # noqa: E402

rid = int(sys.argv[1]) if len(sys.argv) > 1 else 18494
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
cs = deps.confirm
живой = cs._sender
сейчас = datetime.now(timezone.utc)
print("сейчас UTC %s; kill-switch: %s" % (сейчас.strftime("%H:%M"), живой.gates.check_global().tripped))

строка = cs.get(rid)
inn = строка.get("inn")
print("карточка #%d %s ИНН %s кампания %s" % (rid, строка.get("email"), inn, строка.get("campaign_id")))
print("  letter_division:", cs.letter_division(строка))
cards = cs._cards
if cards is not None and getattr(cards, "active", False):
    g = getattr(cards, "divisions", None)
    print("  разрешено компании (divisions):", g(inn) if callable(g) else None, "| division:", cards.division(inn))
try:
    print("  флаги направления:", cs._division_flags(строка) if hasattr(cs, "_division_flags") else "—")
except Exception as ex:  # noqa: BLE001
    print("  флаги: ош", str(ex)[:120])
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
try:
    print("  sdelki_napr:", c.execute("SELECT meyer, kc, sc, detali FROM sdelki_napr WHERE inn=?", (str(inn),)).fetchone())
except Exception as ex:  # noqa: BLE001
    print("  sdelki_napr: ош", ex)

итог = Counter()
for mb in cfg.mailboxes():
    ст = store.get_mailbox_state(mb.mailbox_id)
    гейт = живой.gates.check_mailbox(mb.mailbox_id)
    try:
        лим = живой._daily_limit(mb.provider, getattr(ст, "ramp_day", 0) if ст else 0, mb.mailbox_id)
    except Exception:  # noqa: BLE001
        лим = "?"
    ушло = (getattr(ст, "sent_today", 0) if ст and ст.day_key == живой._day_key(сейчас) else 0)
    можно = живой.can_send_now(mb.mailbox_id, now=сейчас, manual=True)
    причина = ("гейт: %s" % (getattr(гейт, "reason", "") or "") if гейт.tripped else
               "пауза" if (ст and ст.paused) else
               "лимит %s/%s" % (ушло, лим) if not можно else "можно (%s/%s)" % (ушло, лим))
    итог[(mb.division, причина.split(":")[0].split(" ")[0])] += 1
    if mb.division and mb.division.startswith("meyer") or not можно:
        print("  %-6s %-42s %s" % (mb.division, mb.mailbox_id, причина[:90]))
print("сводка (направление, состояние):", dict(итог))
print("  _fallback_mailbox(meyer) ->", cs._fallback_mailbox(inn=inn, prefer_division="meyer"))
print("=== ПОЧЕМУ НЕТ ЯЩИКА ===")
