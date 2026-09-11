# -*- coding: utf-8 -*-
"""Вернуть в очередь письма, упавшие на чужом пароле, и закрыть сам ящик.

11.09 в 09:00 МСК автоотправка выбрала ящик a.kozlov@zernosort.ru и за час
положила в failed 1018 писем партии с ответом сервера «535 authentication
failed: Invalid user or password». Пароль ящика не подходит - то есть письма
не ушли и репутацию не тратили, но и из работы выпали: confirm_decide
терминальный статус не трогает, сами они не вернутся.

Ящик помечен владельцем «в спаме, не использовать», но паузу с него кто-то
снял (заодно ноль в send_limits переехал на a.erokhin). Пока он выбираем,
следующее окно повторит то же самое.

    python spasti_failed_agro.py            # вхолостую
    python spasti_failed_agro.py --primenit
"""
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server\ops")
from sender.auto_send import next_slot, window_from             # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402
import varianty_pisma as V                                      # noqa: E402

ЯЩИК = "a.kozlov@zernosort.ru"
ПРИЧИНА = "владелец: ящик в спаме, не использовать"
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
теперь = datetime.now(timezone.utc)
окно = window_from(store, cfg)

st = store.get_mailbox_state(ЯЩИК)
print("ящик %s: пауза=%s, причина=%r"
      % (ЯЩИК, bool(st and getattr(st, "paused", False)),
         str(getattr(st, "pause_reason", "") or "")[:60]))

with store._lock:
    строки = store._conn.execute(
        """SELECT c.id AS cid, c.status AS cst, m.id AS mid, m.last_error,
                  m.mailbox_id, r.tz
             FROM confirm_reviews c JOIN messages m ON c.message_id = m.id
             LEFT JOIN recipients r ON c.recipient_id = r.id
            WHERE c.subject IN (%s) AND m.status='failed'"""
        % ",".join("?" * len(V.ТЕМЫ)), tuple(V.ТЕМЫ)).fetchall()

счёт = Counter()
вернуть = []
for р in строки:
    т = str(р["last_error"] or "").lower()
    if "auth failed" in т or "5.7.8" in т or "535" in т:
        вернуть.append((int(р["cid"]), int(р["mid"]),
                        str(р["tz"] or "Europe/Moscow")))
        счёт["ВЕРНУТЬ (пароль не подошёл)"] += 1
    else:
        счёт["оставить (%s)" % ("отказ по спаму" if "5.7.1" in т else "прочее")] += 1

if ПРИМЕНИТЬ:
    # 1. закрыть ящик обратно - решение владельца записано в самой причине
    if not (st and getattr(st, "paused", False)):
        store.set_mailbox_paused(ЯЩИК, True, reason=ПРИЧИНА)
        счёт["ЯЩИК ЗАКРЫТ ОБРАТНО"] = 1
    # 2. вернуть письма в работу: письмо в pending_review, карточка в pending
    возвращено = 0
    for нач in range(0, len(вернуть), 400):
        with store.transaction() as conn:
            for cid, mid, зона in вернуть[нач:нач + 400]:
                когда = next_slot(окно, зона, теперь)
                conn.execute(
                    "UPDATE messages SET status='pending_review', "
                    "       last_error=NULL, mailbox_id=NULL, attempt_count=0, "
                    "       scheduled_at=?, updated_at=datetime('now') "
                    " WHERE id=? AND status='failed'",
                    (когда.strftime("%Y-%m-%dT%H:%M:%S.%f"), mid))
                conn.execute(
                    "UPDATE confirm_reviews SET status='pending', reason=NULL, "
                    "       decided_at=NULL, decided_by=NULL, "
                    "       updated_at=datetime('now') "
                    " WHERE id=? AND status<>'sent'", (cid,))
                возвращено += 1
    счёт["ВОЗВРАЩЕНО В ОЧЕРЕДЬ"] = возвращено

print("")
print("=" * 74)
print("=== СПАСЕНИЕ УПАВШИХ: %s ==="
      % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН"))
print("писем в failed: %d" % len(строки))
for к, в in счёт.most_common(8):
    print("   %-44s %5d" % (к, в))
if not ПРИМЕНИТЬ:
    print("")
    print("вхолостую. Вернуть — --primenit")
