# -*- coding: utf-8 -*-
"""Последние N отправленных напоминаний: python pokaz_otpravlennyh.py [N]"""
import sqlite3, sys
N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
for r in c.execute("""SELECT id, email, subject, COALESCE(edited_body, body), decided_at, panel_json FROM confirm_reviews
                      WHERE kind='reply' AND status='sent' AND panel_json LIKE '%napominanie%'
                      ORDER BY decided_at DESC LIMIT ?""", (N,)):
    в = "заход" if "заходы" in (r[5] or "") else "шаблон"
    print("=" * 70); print("#%s  %s  [%s]  %s\nТема: %s\n\n%s\n" % (r[0], r[1], в, r[4], r[2], r[3]))
