# -*- coding: utf-8 -*-
"""Поштучное состояние писем, одобренных «В автоотправку» 12.10 (только чтение).

База открывается read-only (mode=ro). Ничего не меняет.
    sostoyanie_23.py [кампания=14]
"""
import json
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402

КАМП = int(sys.argv[1]) if len(sys.argv) > 1 else 14
cfg = Config.load(r"C:\sender\sender.yaml")
c = sqlite3.connect(r"file:C:/sender/sender.db?mode=ro", uri=True, timeout=30)
c.row_factory = sqlite3.Row

print("сейчас UTC %s | локально сервера %s (tz %s)" % (
    datetime.now(timezone.utc).strftime("%m-%d %H:%M:%S"),
    datetime.now().strftime("%m-%d %H:%M:%S"), time.tzname))

print("--- настройки панели ---")
for к in ("auto_send_enabled", "sending_window"):
    try:
        р = c.execute("SELECT value FROM panel_settings WHERE key=?", (к,)).fetchone()
        print("   %s = %s" % (к, (р[0] if р else None)))
    except Exception as e:  # noqa: BLE001
        print("   %s: %s" % (к, e))
for к in ("service.smtp_timeout_sec", "provider_split.overflow", "confirm.live_send",
          "send_pacing.min_interval_sec", "send_pacing.per_region_interval_sec"):
    try:
        print("   cfg %s = %s" % (к, cfg.get(к, None)))
    except Exception as e:  # noqa: BLE001
        print("   cfg %s: %s" % (к, e))

print("--- кампании ---")
for р in c.execute("SELECT id, name, status FROM campaigns WHERE id IN (10,11,%d)" % КАМП):
    print("   #%s %s [%s]" % (р["id"], р["name"], р["status"]))

print("--- письма: последний review approved/edited, кампания %d ---" % КАМП)
строки = c.execute(
    """SELECT m.id, m.status, m.mailbox_id, m.attempt_count ac, m.scheduled_at sch,
              m.claimed_at cl, m.updated_at upd, m.sent_at sa,
              substr(COALESCE(m.last_error,''),1,70) le, r.email, r.tz,
              cr.id rid, cr.status rs, cr.reason, cr.decided_at dec
         FROM messages m JOIN recipients r ON r.id=m.recipient_id
         JOIN confirm_reviews cr ON cr.id=(SELECT MAX(id) FROM confirm_reviews
                                           WHERE message_id=m.id)
        WHERE m.campaign_id=? AND cr.status IN ('approved','edited')
        ORDER BY m.status, m.mailbox_id, m.id""", (КАМП,)).fetchall()
счёт = Counter()
for р in (строки if not ("kratko" in sys.argv) else []):
    pass
for р in строки:
    счёт[(р["status"], р["mailbox_id"] or "-")] += 1
    домен = (р["email"] or "").split("@")[-1]
    if "kratko" in sys.argv:
        continue
    print("   m%-6s %-9s ящ=%-28s поп=%-3s sch=%s cl=%s upd=%s @%s tz=%s | %s"
          % (р["id"], р["status"], (р["mailbox_id"] or "-")[:28], р["ac"],
             str(р["sch"])[5:16], str(р["cl"] or "-")[5:19], str(р["upd"])[5:19],
             домен[:22], р["tz"], р["le"][:60]))
if "spisok" in sys.argv:
    print("   " + " ".join("m%s:%s:%s:%s:%s" % (р["id"], р["status"][:5], (р["mailbox_id"] or "-").split("@")[0], р["ac"], (р["email"] or "").split("@")[-1][:14]) for р in строки))
print("   итого %d: %s" % (len(строки), dict(счёт)))
print("   reason/decided: %s" % Counter((р["reason"], str(р["dec"])[:13]) for р in строки).most_common(3))

print("--- вся одобренная очередь (все кампании), не терминальная ---")
for р in c.execute(
        """SELECT m.campaign_id k, m.status s, COUNT(*) n, MIN(m.scheduled_at) mn
             FROM messages m WHERE m.status IN ('scheduled','sending')
              AND (SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id
                   ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited')
            GROUP BY 1,2"""):
    print("   камп %s %-9s %4d  ближайший срок %s" % (р["k"], р["s"], р["n"], str(р["mn"])[:16]))

КРАТКО = "kratko" in sys.argv
if КРАТКО:
    for р in c.execute("SELECT m.id, m.status, m.mailbox_id, m.attempt_count, m.claimed_at, m.updated_at, substr(COALESCE(m.last_error,''),1,60) le FROM messages m WHERE m.campaign_id=11 AND m.status='sending' LIMIT 4"):
        print("   камп11 sending: %s" % (tuple(р),))
    print("=== СОСТОЯНИЕ 23 (кратко) ===")
    raise SystemExit(0)
print("--- Meyer-ящики: пул, хост, состояние ---")
пулы = cfg.provider_pools() or {}
пул_ящика = {m: п for п, мм in пулы.items() for m in мм}
for мб in cfg.mailboxes():
    if "inspection" not in мб.mailbox_id and str(getattr(мб, "division", "")) != "meyer":
        continue
    ст = c.execute("SELECT * FROM mailbox_state WHERE mailbox_id=?", (мб.mailbox_id,)).fetchone()
    ст = dict(ст) if ст else {}
    print("   %-34s пул=%-12s %s:%s div=%s пауза=%s день=%s отпр=%s посл=%s"
          % (мб.mailbox_id[:34], пул_ящика.get(мб.mailbox_id), мб.smtp_host, мб.smtp_port,
             getattr(мб, "division", None), ст.get("paused"), ст.get("day_key"),
             ст.get("sent_today"), str(ст.get("last_sent_at"))[5:16]))
print("   пулы: %s" % {п: len(мм) for п, мм in пулы.items()})
хосты = Counter((м.smtp_host, м.smtp_port) for м in cfg.mailboxes())
print("   SMTP-хосты всех ящиков: %s" % dict(хосты))

print("--- последний реальный sent и события за 6 ч ---")
р = c.execute("SELECT id, mailbox_id, sent_at FROM messages WHERE status='sent' "
              "ORDER BY sent_at DESC LIMIT 1").fetchone()
print("   последний sent: %s" % (dict(р) if р else None))
for р in c.execute("SELECT * FROM events ORDER BY id DESC LIMIT 1"):
    print("   последнее событие: %s" % {k: str(р[k])[:40] for k in р.keys()})
print("=== СОСТОЯНИЕ 23 ===")
