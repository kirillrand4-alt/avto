# -*- coding: utf-8 -*-
"""Сколько готовых писем идёт на адреса, которых проба подтвердить не может.

Гейт репутации по ящику сработал на a.balakirev@compressor-store.ru: 4
отбивки на 50 писем (8% при пороге 2.5%). Три из четырёх - «invalid mailbox»
от Mail.ru: домен получателя стоит на Mail.ru, тот на пробе отвечает «приму»
про ЛЮБОЙ адрес (catch-all), а на настоящем письме выясняется, что ящика
нет. То есть эти отбивки проба поймать не могла в принципе.

Считаем, сколько такого риска ещё лежит в готовых письмах: разбивка по
вердикту пробы и по провайдеру почты получателя.

    python zapusk_svoego_skripta.py ops/gotovye_riski_otbivki.py
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    ряд = store._conn.execute(
        "SELECT c.email, COALESCE(p.verdict,'(не проверялся)'), "
        "       COALESCE(r.mx_provider,'?') "
        "FROM confirm_reviews c "
        "LEFT JOIN addr_probe p ON p.email = lower(c.email) "
        "LEFT JOIN recipients r ON r.id = c.recipient_id "
        "WHERE c.status='approved'").fetchall()

по_вердикту = Counter()
по_провайдеру = Counter()
рискованные = Counter()
for email, вердикт, провайдер in ряд:
    по_вердикту[вердикт] += 1
    по_провайдеру[провайдер] += 1
    if вердикт in ("принимает всё", "неясно", "(не проверялся)"):
        рискованные[провайдер] += 1

print(f"готовых писем: {len(ряд)}\n")
print("вердикт пробы:")
for в, n in по_вердикту.most_common():
    print(f"  {в:<20} {n:>5}")
print("\nпочтовый провайдер получателя:")
for п, n in по_провайдеру.most_common(10):
    print(f"  {п:<20} {n:>5}")
print(f"\nписем, где проба НЕ подтверждает ящик "
      f"(«принимает всё» / «неясно» / без пробы): {sum(рискованные.values())}")
for п, n in рискованные.most_common(10):
    print(f"  {п:<20} {n:>5}")
