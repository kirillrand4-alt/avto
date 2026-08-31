# -*- coding: utf-8 -*-
"""Отправить письмо 12599 «Кубаночке» — по прямой команде владельца.

Путь тот же, что кнопка «Отправить» в панели: build_deps собирает
ConfirmSend с боевым Sender (confirm.live_send=true), approve уходит
немедленно по SMTP. Ручная отправка разрешена; холд на автоматике не
трогаем.
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402
from sender.wiring import build_deps                          # noqa: E402

ОБЗОР = 12599
ОТПРАВИТЬ = "--otpravit" in sys.argv

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
print("confirm.live_send: %s" % cfg.get("confirm.live_send", False))
deps = build_deps(cfg, store, dry_run=True)
cs = deps.confirm
print("боевой отправитель подключён: %s" % (cs._sender is not None))

row = store.confirm_get(ОБЗОР) if hasattr(store, "confirm_get") else None
if row is None:
    with store._lock:
        r = store._conn.execute("SELECT * FROM confirm_reviews WHERE id=?",
                                (ОБЗОР,)).fetchone()
    row = dict(r) if r else None
print("\nкарточка %s: статус=%s, кому=%s, тема=%s"
      % (ОБЗОР, row.get("status"), row.get("email"),
         str(row.get("subject"))[:60]))

# Ручное письмо из /confirm/novoe создаётся БЕЗ строки в messages, а
# approve без неё падает «нечего отправлять». Заводим её тем же способом,
# что генерация (AiQuota._ensure_message), и привязываем к карточке.
if row.get("message_id") is None:
    print("\nу карточки нет письма в messages — завожу")
    from sender.ai_quota import AiQuota
    q = AiQuota(store, db_path=cfg.get("service.db_path",
                                       r"C:\sender\sender.db"), config=cfg)
    mid, step_id, почему = q._ensure_message(int(row["campaign_id"]),
                                             int(row["recipient_id"]))
    print("   message_id=%s, шаг=%s %s" % (mid, step_id, почему))
    if not mid:
        print("   не завелось — выхожу")
        raise SystemExit(1)
    if ОТПРАВИТЬ:
        store.confirm_set_message(int(ОБЗОР), int(mid))
        print("   привязано к карточке")

if not ОТПРАВИТЬ:
    print("\n[сухой прогон] отправить — с ключом --otpravit")
    raise SystemExit(0)

try:
    ок = cs.approve(ОБЗОР, operator="kirill (команда владельца)")
    print("\napprove вернул: %s" % ок)
except Exception as e:                                        # noqa: BLE001
    print("\nОТПРАВКА НЕ ПРОШЛА: %s: %s" % (type(e).__name__, str(e)[:220]))
    raise SystemExit(1)

with store._lock:
    r = store._conn.execute(
        "SELECT cr.status, cr.decided_at, cr.message_id, m.status ms,"
        "       m.sent_at, m.last_error, m.rfc_message_id"
        "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id"
        " WHERE cr.id=?", (ОБЗОР,)).fetchone()
print("\n=== ИТОГ ===")
if r:
    print("карточка: %s, решено %s" % (r["status"], r["decided_at"]))
    print("письмо:   статус %s, отправлено %s" % (r["ms"], r["sent_at"]))
    print("Message-ID: %s" % r["rfc_message_id"])
    if r["last_error"]:
        print("ошибка:   %s" % str(r["last_error"])[:200])
