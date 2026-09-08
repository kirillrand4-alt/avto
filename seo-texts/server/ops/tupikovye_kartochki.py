# -*- coding: utf-8 -*-
"""Карточки партии, подтверждение которых ничего не сделает.

confirm_decide на approve переписывает тему и тело письма из карточки, но
только «WHERE status NOT IN ('sent','skipped','failed')». Если письмо уже в
терминальном статусе, оператор нажмёт «Отправить», карточка станет
approved, а письмо не уедет никогда - и никто этого не заметит.

Такое возможно потому, что _ensure_message переиспользует письмо той же
кампании для того же получателя: компании, которой Meyer уже писал в
августе, новая карточка досталась вместе со старым письмом.
"""
import sys
from collections import Counter

ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                 # noqa: E402

ТЕМА = "Для качества: вопрос по сортировке зерна"
ТЕРМИНАЛЬНЫЕ = ("sent", "skipped", "failed")
store = Store(r"C:\sender\sender.db")
счёт = Counter()
тупики = []
with store._lock:
    for р in store._conn.execute(
            """SELECT c.id AS cid, c.status AS cst, c.email, c.message_id,
                      m.id AS mid, m.status AS mst, m.sent_at
                 FROM confirm_reviews c LEFT JOIN messages m
                      ON c.message_id = m.id
                WHERE c.subject=?""", (ТЕМА,)):
        if str(р["cst"]) != "pending":
            continue
        ст = str(р["mst"] or "нет письма")
        счёт[ст] += 1
        if ст in ТЕРМИНАЛЬНЫЕ or ст == "нет письма":
            тупики.append((р["cid"], р["email"], ст, р["sent_at"]))
# ПОДНИМАЕМ ПИСЬМО ВСЛЕД ЗА КАРТОЧКОЙ. Ровно это делает confirm_submit,
# когда оживляет снятую карточку: «оживить одну карточку мало - строка
# письма осталась бы снятой, и оператор подтверждал бы то, чего
# автоотправка не видит». Здесь тот же случай, только карточка не
# оживлялась, а получила чужое письмо от _ensure_message.
поднято = 0
if ПРИМЕНИТЬ and тупики:
    with store.transaction() as conn:
        for cid, _а, ст, _к in тупики:
            if ст != "skipped":
                continue
            cur = conn.execute(
                "UPDATE messages SET status='pending_review', last_error=NULL,"
                "       updated_at=datetime('now') "
                " WHERE id=(SELECT message_id FROM confirm_reviews WHERE id=?)"
                "   AND status='skipped'", (cid,))
            поднято += int(cur.rowcount or 0)

for cid, а, ст, когда in тупики[:20]:
    print("   карточка %-7s %-32s письмо %-8s отправлено %s"
          % (cid, str(а)[:32], ст, когда))
print("")
print("=" * 74)
print("=== ЧТО СТОИТ ЗА PENDING-КАРТОЧКАМИ ПАРТИИ ===")
for к, в in счёт.most_common():
    print("   письмо в статусе %-16s %5d" % (к, в))
print("подтверждение не сработало бы у: %d карточек" % len(тупики))
if ПРИМЕНИТЬ:
    print("писем поднято обратно в pending_review: %d" % поднято)
else:
    print("вхолостую. Поднять письма — --primenit")
