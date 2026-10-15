# -*- coding: utf-8 -*-
"""Текст лида: lid_tekst.py <id>"""
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db")
р = c.execute("SELECT id, email, status, need FROM leads WHERE id=?", (int(sys.argv[1]),)).fetchone()
print(р[0], р[1], р[2])
print(str(р[3])[-1200:])
print("=== ЛИД ===")
