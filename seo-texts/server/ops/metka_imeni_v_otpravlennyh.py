# -*- coding: utf-8 -*-
"""Уходила ли метка ИМЯ_ОТПРАВИТЕЛЯ к клиентам: отправленные письма кампании (body_rendered) и карточки
(body) с меткой. Только чтение.  metka_imeni_v_otpravlennyh.py <campaign_id>"""
import sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
k = int(sys.argv[1]); M = "%ИМЯ_ОТПРАВИТЕЛЯ%"
print("отправлено:", c.execute("SELECT count(*) FROM messages WHERE campaign_id=? AND status='sent'", (k,)).fetchone()[0],
      "| с меткой в отправленном тексте:", c.execute("SELECT count(*) FROM messages WHERE campaign_id=? AND status='sent' AND body_rendered LIKE ?", (k, M)).fetchone()[0],
      "| карточек с меткой (отправлены):", c.execute("SELECT count(*) FROM confirm_reviews WHERE campaign_id=? AND status IN ('sent','approved') AND body LIKE ?", (k, M)).fetchone()[0])
