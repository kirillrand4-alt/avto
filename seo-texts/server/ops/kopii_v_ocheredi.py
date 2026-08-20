# -*- coding: utf-8 -*-
"""Письма в очереди, которые идут на ВТОРОЙ адрес компании: копии.

Владелец: «если это копия письма для другого контакта — проверь глазами
имя адресата и то, что там написали, поправь имя если копия стала чисто
копией, и отправь».

Копией считаем карточку, у которой той же компании (по ИНН) мы уже
отправляли письмо, но НА ДРУГОЙ адрес. Тогда письмо законно: пишем
второму человеку. Но текст мог остаться обращённым к первому.
"""
import sqlite3
import sys
from collections import Counter

ПОКАЗАТЬ = int(next((a for a in sys.argv[1:] if a.isdigit()), "0"))
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

ряды = c.execute(
    "SELECT cr.id, cr.email, cr.subject, cr.body, cr.campaign_id, "
    "       r.inn, r.company_name, r.contact_name "
    "FROM confirm_reviews cr LEFT JOIN recipients r ON r.id=cr.recipient_id "
    "WHERE cr.status='pending' ORDER BY cr.id").fetchall()

счёт = Counter()
копии = []
for r in ряды:
    инн = "".join(ch for ch in str(r["inn"] or "") if ch.isdigit())
    почта = str(r["email"] or "").strip().lower()
    if not инн:
        счёт["без ИНН — не судим"] += 1
        continue
    ушло = c.execute(
        "SELECT email, ts FROM send_log WHERE inn=? ORDER BY ts", (инн,)
    ).fetchall()
    if not ушло:
        счёт["компании ещё не писали"] += 1
        continue
    адреса = {str(x["email"] or "").lower() for x in ушло}
    if почта in адреса:
        счёт["ЭТОМУ адресу уже писали — не копия, дубль"] += 1
        continue
    копии.append((r, [dict(x) for x in ушло]))
    счёт["КОПИЯ: другой контакт той же компании"] += 1

print(f"в очереди: {len(ряды)}")
for k, n in счёт.most_common():
    print(f"  {n:>4}  {k}")

print(f"\n== копии ({len(копии)}) ==")
for r, ушло in копии:
    print(f"  #{r['id']} {str(r['company_name'])[:34]:<34} "
          f"кому сейчас: {r['email']:<28} раньше: "
          f"{', '.join(x['email'] for x in ушло)[:60]}")

if ПОКАЗАТЬ:
    for r, _ушло in копии[:ПОКАЗАТЬ]:
        print("\n" + "=" * 74)
        print(f"#{r['id']} {r['company_name']} | контакт в карточке: "
              f"{r['contact_name'] or '(нет)'} | кому: {r['email']}")
        print(f"ТЕМА: {r['subject']}")
        print(str(r["body"] or "")[:1100])
