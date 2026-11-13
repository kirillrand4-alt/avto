# -*- coding: utf-8 -*-
"""Снять из автоотправки письма, которые падают каждый проход UnicodeEncodeError (кириллица в адресе получателя):
20520, 42885, 21116 + любые scheduled с не-ASCII адресом. Они стоят первыми в очереди и, похоже, обрывают проход —
с 09:57 13.11 автоотправка не отправила ни одного письма. Статус → failed (не повторять). Обратимо руками.
    snyat_bitye_kirillica.py [--primenit]"""
import re, sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60); c.execute("PRAGMA busy_timeout=60000")
ряды = c.execute("SELECT m.id, m.campaign_id, m.status, r.email, m.attempt_count FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                 "WHERE m.status IN ('scheduled','sending','failed') ").fetchall()
бит = [р for р in ряды if р[0] in (20520, 42885, 21116) or (р[2] != 'failed' and re.search(r"[^\x00-\x7f]", р[3] or ""))]
for р in бит: print("  #%s камп %s %s попыток %s домен %s" % (р[0], р[1], р[2], р[4], (р[3] or "").split("@")[-1]))
if "--primenit" in sys.argv:
    for р in бит:
        c.execute("UPDATE messages SET status='failed', last_error='адрес получателя не ASCII (кириллица) — SMTP не принимает; снято 13.11' WHERE id=?", (р[0],))
        # цикл может вернуть письмо в scheduled своим mark_failed(retryable) — снимаем одобрение карточки: claim берёт только approved
        c.execute("UPDATE confirm_reviews SET status='skipped', reason='адрес не ASCII, снято 13.11' WHERE message_id=?", (р[0],))
    c.commit(); print("снято:", len(бит))
else: print("к снятию:", len(бит))
