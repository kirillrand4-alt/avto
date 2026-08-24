# -*- coding: utf-8 -*-
"""Сколько подписей в письме клиента — и повторная отправка копий владельцу.

Владелец 24.08: «пришли оба, но почему-то по две подписи». Копии я собрал из
messages.body_rendered — это текст УЖЕ отправленного письма, в нём подпись
есть, и отправка дописала вторую. Проверяем, что у клиентов подпись одна:
черновик (confirm_reviews.body) не должен её содержать, отправленное —
должно, ровно один раз.

С --катить шлём копии заново, беря ЧЕРНОВИК.
"""
import re
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.dtos import MessageIn, RecipientIn, RenderedMessage     # noqa: E402
from sender.store import Store                                      # noqa: E402
from sender.wiring import build_deps                                # noqa: E402

КАТИТЬ = "--катить" in sys.argv or "--katit" in sys.argv
АДРЕСА = ["kirill.martyuschov@yandex.ru", "kirillrand4@gmail.com"]
ПОДПИСЬ = re.compile(r"ООО\s*«Руспром»,\s*ИНН")
УВАЖ = re.compile(r"С уважением,")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

print("=== СКОЛЬКО ПОДПИСЕЙ В НАСТОЯЩИХ ПИСЬМАХ ===")
строки = store._conn.execute(
    "SELECT m.id, m.subject, m.body_rendered, m.mailbox_id, m.campaign_id, "
    "       m.sequence_step_id, cr.id crid, cr.body draft, cr.edited_body "
    "  FROM messages m "
    "  LEFT JOIN confirm_reviews cr ON cr.message_id = m.id "
    " WHERE m.status='sent' AND m.body_rendered IS NOT NULL "
    "   AND LENGTH(m.body_rendered) > 400 "
    " ORDER BY m.sent_at DESC LIMIT 12").fetchall()
плохих = 0
for с in строки:
    отпр = str(с["body_rendered"] or "")
    чер = str(с["edited_body"] or с["draft"] or "")
    н_отпр = len(ПОДПИСЬ.findall(отпр))
    н_чер = len(ПОДПИСЬ.findall(чер))
    if н_отпр > 1:
        плохих += 1
    print("  письмо #%-6s отправлено: подписей %d, «С уважением» %d | "
          "черновик: подписей %d %s"
          % (с["id"], н_отпр, len(УВАЖ.findall(отпр)), н_чер,
             "" if н_отпр == 1 else "  ← ЗАДВОЕНИЕ"))
print("  писем с задвоенной подписью среди 12 последних: %d" % плохих)

if not КАТИТЬ:
    print("\nсухой прогон. Повторная отправка копий — --катить")
    raise SystemExit(0)

# --- копии заново, из ЧЕРНОВИКА ------------------------------------------ #
deps = build_deps(cfg, store, dry_run=True)
живой = getattr(deps.confirm, "_sender", None)
if живой is None or getattr(живой, "dry_run", False):
    print("живой отправитель не готов — стоп")
    raise SystemExit(1)

годные = []
домены = set()
for с in строки:
    чер = str(с["edited_body"] or с["draft"] or "")
    if not чер or ПОДПИСЬ.search(чер):
        continue                      # черновика нет или он уже с подписью
    д = str(с["mailbox_id"] or "").split("@")[-1]
    if not д or д in домены:
        continue
    домены.add(д)
    годные.append((с, чер))
    if len(годные) == 2:
        break
if not годные:
    print("не нашёл черновиков без подписи — стоп")
    raise SystemExit(1)

print("\n=== ОТПРАВКА КОПИЙ (текст из черновика) ===")
ушло = 0
for с, чер in годные:
    print("\n  письмо-источник #%s | ящик %s | тема: %s"
          % (с["id"], с["mailbox_id"], с["subject"]))
    print("  хвост черновика: …%s" % чер.rstrip()[-90:].replace("\n", " ⏎ "))
    for адрес in АДРЕСА:
        try:
            rid = store.upsert_recipient(RecipientIn(
                email=адрес, domain=адрес.split("@")[-1],
                company_name="ПРОВЕРКА ДОСТАВКИ (владелец)",
                source="проверка-доставки", tz="Europe/Moscow"))
            mid, _ = store.enqueue_message(MessageIn(
                idempotency_key="proverka2-%s-%s-%d" % (
                    с["id"], адрес.split("@")[0], int(time.time())),
                campaign_id=с["campaign_id"], recipient_id=rid,
                sequence_step_id=с["sequence_step_id"],
                scheduled_at=datetime.now(timezone.utc)), status="scheduled")
            рез = живой.send(store.get_message(int(mid)),
                             RenderedMessage(subject=str(с["subject"]), body=чер),
                             с["mailbox_id"], manual=True, to_email=адрес)
            ушло += 1
            print("    УШЛО: %s | письмо %s | rfc %s"
                  % (адрес, mid, str(getattr(рез, "rfc_message_id", ""))[:50]))
        except Exception as e:  # noqa: BLE001
            print("    СБОЙ: %s | %s: %s" % (адрес, type(e).__name__, str(e)[:120]))
print("\nушло: %d" % ушло)
