# -*- coding: utf-8 -*-
"""Показать тела писем перед правкой: десять сегодняшних и одно вебинарное.

Правим вслепую только дураки: надо видеть, КАК ссылка вплетена в текст,
чтобы вырезать её вместе с фразой, а не оставить обрубок. И надо знать,
есть ли ссылка в вебинарных - у них она может быть смыслом письма
(регистрация), тогда вырезать нельзя.
"""
import re
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ид = [3413, 3424, 3648, 3657, 3666, 3669, 3693, 3701, 3762, 3764]
р = c.execute("SELECT id, email, subject, COALESCE(edited_body,body,'') тело "
              "FROM confirm_reviews WHERE id=?", (ид[0],)).fetchone()
print("=== ОДНО ИЗ ДЕСЯТИ (целиком) ===")
print(f"#{р['id']} {р['email']}\nТЕМА: {р['subject']}\n")
print(р["тело"])

print("\n=== ССЫЛКИ В ЭТИХ ДЕСЯТИ ===")
for и in ид:
    р = c.execute("SELECT id, COALESCE(edited_body,body,'') тело "
                  "FROM confirm_reviews WHERE id=?", (и,)).fetchone()
    сс = re.findall(r"https?://\S+", р["тело"] or "")
    print(f"  #{и}: {сс or 'ссылок нет'}")

print("\n=== ВЕБИНАРНЫЕ: есть ли ссылки ===")
ряды = c.execute(
    "SELECT id, COALESCE(edited_body,body,'') тело FROM confirm_reviews "
    "WHERE dedup_key LIKE 'vebinar28:%' AND status='pending'").fetchall()
со_ссылкой = 0
образец = None
for р in ряды:
    сс = re.findall(r"https?://\S+", р["тело"] or "")
    if сс:
        со_ссылкой += 1
        образец = образец or (р["id"], сс)
print(f"вебинарных pending: {len(ряды)}, из них со ссылкой: {со_ссылкой}")
if образец:
    print(f"пример #{образец[0]}: {образец[1]}")
if ряды:
    print(f"\n=== ОДНО ВЕБИНАРНОЕ (целиком) ===\n{ряды[0]['тело']}")
