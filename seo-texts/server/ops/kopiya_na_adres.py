# -*- coding: utf-8 -*-
"""Копия отправленного письма на исправленный адрес компании (в очередь подтверждения).

Владелец 13.10: «ontrol@profi.bio … поставь на правильную почту копию письма».
Проба нового адреса (вердикт в три базы), новый получатель с тем же ИНН и
карточкой, письмо — тот же текст и тема, что ушли на ошибочный адрес; ложится
pending_review, отправляет оператор.

    kopiya_na_adres.py <старый адрес> <новый адрес>
"""
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.ai_quota import build_ai_quota  # noqa: E402
from sender.confirm import ConfirmSend  # noqa: E402
from sender.suppression import Suppression  # noqa: E402
from sender.addr_probe import build_addr_probe  # noqa: E402

старый, новый = sys.argv[1].lower(), sys.argv[2].lower()
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))
_п = build_addr_probe(store, cfg)
проба = getattr(_п, "probe", None) or getattr(_п, "probe_")
рез = проба.probe(новый)
вер = str(рез.get("verdict") or "неясно")
print("проба %s: %s (%s)" % (новый, вер, str(рез.get("answer") or "")[:100]))
ts = int(time.time())
cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
ox = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
р = c.execute("SELECT * FROM recipients WHERE lower(email)=?", (старый,)).fetchone()
if р is None:
    print("получателя со старым адресом нет")
    sys.exit(0)
with cx:
    if not cx.execute("SELECT 1 FROM emails WHERE inn=? AND lower(email)=?", (р["inn"], новый)).fetchone():
        старая = cx.execute("SELECT role FROM emails WHERE inn=? AND lower(email)=?", (р["inn"], старый)).fetchone()
        cx.execute("INSERT INTO emails (inn, email, role, source) VALUES (?,?,?,?)",
                   (р["inn"], новый, старая[0] if старая else None, "ispravlen-13-10"))
    cx.execute("UPDATE emails SET probe_verdict=?, probe_ts=? WHERE lower(email)=?", (вер, ts, новый))
with ox:
    ox.execute("CREATE TABLE IF NOT EXISTS email_probe (email TEXT PRIMARY KEY, verdict TEXT, source TEXT, answer TEXT, ts INTEGER)")
    ox.execute("INSERT INTO email_probe (email, verdict, source, answer, ts) VALUES (?,?,?,?,?) ON CONFLICT(email) "
               "DO UPDATE SET verdict=excluded.verdict, ts=excluded.ts", (новый, вер, "smtp-server", "", ts))
if вер in ("нет ящика", "нет MX"):
    print("новый адрес тоже мёртв — копию не ставлю")
    print("=== КОПИЯ: НЕ ПОСТАВЛЕНА ===")
    sys.exit(0)
м = c.execute("SELECT * FROM messages WHERE recipient_id=? AND status IN ('sent','bounced') ORDER BY sent_at DESC LIMIT 1",
              (р["id"],)).fetchone()
тело, тема = м["body_rendered"], м["subject"]
if not тело:
    cr = c.execute("SELECT coalesce(edited_body, body), coalesce(edited_subject, subject) FROM confirm_reviews "
                   "WHERE message_id=? ORDER BY id DESC LIMIT 1", (м["id"],)).fetchone()
    тело, тема = cr[0], cr[1]
есть = c.execute("SELECT id FROM recipients WHERE lower(email)=?", (новый,)).fetchone()
if есть:
    нов_id = есть[0]
else:
    теперь = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    with c:
        cur = c.execute("INSERT INTO recipients (inn,email,domain,company_name,okved,segment,contact_name,source,region,"
                        "extra_json,tz,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (р["inn"], новый, новый.split("@")[-1], р["company_name"], р["okved"], р["segment"],
                         р["contact_name"], "ispravlen-13-10", р["region"], р["extra_json"], р["tz"], теперь, теперь))
        нов_id = cur.lastrowid
mid, _шаг, почему = q._ensure_message(м["campaign_id"], нов_id)
if not mid:
    print("message не создан: %s" % почему)
    sys.exit(0)
r = cs.submit(email=новый, subject=тема, body=тело, inn=р["inn"], campaign_id=м["campaign_id"],
              recipient_id=нов_id, message_id=mid, panel={"kopiya_s": старый})
print("копия письма m%s → %s: очередь %s (review %s)" % (м["id"], новый, r.status, r.review_id))
print("=== КОПИЯ: ПОСТАВЛЕНА ===")
