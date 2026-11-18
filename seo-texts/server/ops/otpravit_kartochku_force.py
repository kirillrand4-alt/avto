# -*- coding: utf-8 -*-
"""Ручная отправка одной карточки в обход заслонов по прямому слову владельца (approve force=True, след в аудите).
Снятую панелью автоматически (auto:...) карточку сначала возвращает в pending. Отписку/жалобу/мёртвый адрес approve
не обходит. Владелец 18.11: «отправь такое же письмо инженеру их» (бухгалтер ответила и дала адрес гл. инженера).
    otpravit_kartochku_force.py <id карточки> "<кто/почему>" [--primenit]"""
import sqlite3, sys, time
sys.path.insert(0, r"C:\sender")
from sender.config import Config
from sender.store import Store
from sender.wiring import build_deps
РИД = int(sys.argv[1]); КТО = sys.argv[2]; ПРИМ = "--primenit" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml"); st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
к = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
р = к.execute("SELECT id, status, reason, email, subject, message_id FROM confirm_reviews WHERE id=?", (РИД,)).fetchone()
print("карточка:", р)
if not ПРИМ: print("сухой прогон"); sys.exit(0)
т = time.strftime("%Y-%m-%dT%H:%M:%S")
if р[1] == "skipped" and str(р[2] or "").startswith("auto:"):
    with к:
        к.execute("UPDATE confirm_reviews SET status='pending', reason=NULL, decided_at=NULL, updated_at=? WHERE id=?", (т, РИД))
        if р[5]: к.execute("UPDATE messages SET status='pending_review', last_error=NULL, updated_at=? WHERE id=? AND status='skipped'", (т, р[5]))
cs = build_deps(cfg, st, dry_run=False).confirm
print("отправка:", cs.approve(РИД, operator=КТО, force=True))
print("после:", к.execute("SELECT id, status, reason FROM confirm_reviews WHERE id=?", (РИД,)).fetchone(),
      к.execute("SELECT status, sent_at, last_error FROM messages WHERE id=?", (р[5],)).fetchone())
