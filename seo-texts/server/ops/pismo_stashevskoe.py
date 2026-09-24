# -*- coding: utf-8 -*-
"""Всё про ответ «Сташевского»: текст, наше письмо, ящики, карточка лида.

Владелец: письмо из ленты не открывается. Собираем содержимое напрямую из
базы и из живого ящика, и заодно смотрим, чего не хватает карточке, чтобы
лента его показала.
"""
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

СОБЫТИЕ = int(sys.argv[1]) if len(sys.argv) > 1 else 416761
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
вых = []
with store._lock:
    c = store._conn
    е = c.execute("SELECT * FROM events WHERE id=?", (СОБЫТИЕ,)).fetchone()
    if not е:
        raise SystemExit("события %s нет" % СОБЫТИЕ)
    кол = [x[1] for x in c.execute("PRAGMA table_info(events)")]
    вых.append("--- событие %s ---" % СОБЫТИЕ)
    for k in кол:
        if k == "detail_json":
            continue
        if е[k] not in (None, ""):
            вых.append("   %-16s %s" % (k, str(е[k])[:100]))

    д = {}
    try:
        д = json.loads(е["detail_json"] or "{}")
    except Exception:                                           # noqa: BLE001
        pass
    ш = д.get("headers") or {}
    вых.append("")
    вых.append("--- заголовки входящего ---")
    for имя in ("From", "Reply-To", "Return-Path", "To", "Cc", "Subject",
                "Date", "Message-ID", "In-Reply-To"):
        if ш.get(имя):
            вых.append("   %-12s %s" % (имя, str(ш[имя])[:110]))
    вых.append("")
    вых.append("--- текст ответа (snippet) ---")
    for с in str(д.get("snippet") or "").splitlines()[:40]:
        вых.append("   " + с[:150])
    вых.append("")
    вых.append("   прочие поля detail: %s"
               % ", ".join(k for k in д if k not in ("headers", "snippet")))
    for k in ("reply_kind", "phone", "inbox_mailbox", "references"):
        if д.get(k):
            вых.append("   %-14s %s" % (k, str(д[k])[:100]))

    рид = е["recipient_id"]
    вых.append("")
    вых.append("--- получатель %s ---" % рид)
    п = c.execute("SELECT * FROM recipients WHERE id=?", (рид,)).fetchone()
    if п:
        for k in ("id", "email", "company_name", "inn", "region"):
            try:
                вых.append("   %-14s %s" % (k, п[k]))
            except Exception:                                   # noqa: BLE001
                pass

    вых.append("")
    вых.append("--- наши письма этому получателю ---")
    for м in c.execute(
            "SELECT id, status, subject, sent_at, mailbox_id, campaign_id, "
            "       thread_id, rfc_message_id FROM messages "
            " WHERE recipient_id=? ORDER BY id", (рид,)):
        вых.append("   письмо %-7s %-8s %s  ящик %s"
                   % (м["id"], м["status"], str(м["sent_at"])[:16],
                      м["mailbox_id"]))
        вых.append("       тема: %s" % str(м["subject"])[:80])
        вых.append("       ветка: %s  msgid: %s"
                   % (м["thread_id"], str(м["rfc_message_id"])[:60]))

    вых.append("")
    вых.append("--- карточка лида ---")
    кл = [x[1] for x in c.execute("PRAGMA table_info(leads)")]
    строки = c.execute("SELECT * FROM leads WHERE recipient_id=? OR email=?",
                       (рид, (п["email"] if п else ""))).fetchall()
    вых.append("   карточек: %d" % len(строки))
    for л in строки:
        for k in кл:
            if л[k] in (None, ""):
                continue
            s = str(л[k])
            if len(s) > 100:
                вых.append("   --- %s ---" % k)
                вых.append(s[:1500])
            else:
                вых.append("   %-16s %s" % (k, s))

print("\n".join(вых))
print("")
print("=" * 74)
print("=== ОТВЕТ СТАШЕВСКОГО ===")
