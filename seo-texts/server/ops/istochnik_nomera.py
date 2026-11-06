# -*- coding: utf-8 -*-
"""Откуда номер/адрес компании: все строки phone_contacts, people, email_sources, obzvon по ИНН. istochnik_nomera.py ИНН"""
import sqlite3, sys
inn = sys.argv[1]
e = sqlite3.connect("file:C:\\sender\\enrich.db?mode=ro", uri=True, timeout=30)
o = sqlite3.connect("file:C:\\sender\\obzvon-index.db?mode=ro", uri=True, timeout=30)
for t, q in [("phone_contacts", "SELECT phone, person, role, source, source_url, updated_at FROM phone_contacts WHERE inn=?"),
             ("people", "SELECT person, post, phone, email, source, source_url FROM people WHERE inn=?"),
             ("emails", "SELECT email, role, source, source_url FROM emails WHERE inn=?"),
             ("companies", "SELECT phones, site, istochnik_rekvizitov FROM companies WHERE inn=?")]:
    for r in e.execute(q, (inn,)):
        print(t, r)
for r in o.execute("SELECT phones_base, emails_base, phones_site, emails_site, sites, base_label FROM obzvon WHERE inn=?", (inn,)):
    print("obzvon", r)
