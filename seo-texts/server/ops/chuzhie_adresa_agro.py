# -*- coding: utf-8 -*-
"""Адреса партии, которые похожи не на почту хозяйства, а на чужую службу.

В карточках Чеко попадаются адреса, взятые из вакансий и объявлений:
центр занятости населения (czn/zan), кадровые и бухгалтерские конторы.
Письмо туда уйдёт не тому, кто покупает.
"""
import re, sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                 # noqa: E402

ТЕМА = "для качества: вопрос по сортировке зерна"
ПРИЗНАКИ = [
    ("центр занятости", re.compile(r"(?i)(^|[^a-z])czn|czn\.|zan\.|zanyat|"
                                   r"trud[a-z]*\.|rabota\.|szn\.")),
    ("госпочта .gov/.gov.ru", re.compile(r"(?i)@[a-z0-9.\-]*gov\.")),
    ("админрайон/мэрия", re.compile(r"(?i)@[a-z0-9.\-]*(adm|admin|mo-|raion|"
                                    r"mr-|okrug)[a-z0-9.\-]*\.")),
    ("почта на бесплатном + слово kadr/hr", re.compile(r"(?i)(kadr|hr[-_.]|ok@)")),
]
store = Store(r"C:\sender\sender.db")
счёт = Counter()
примеры = {}
всего = 0
with store._lock:
    for р in store._conn.execute(
            "SELECT id, email, status FROM confirm_reviews WHERE subject=?",
            (ТЕМА,)):
        всего += 1
        а = str(р["email"] or "")
        for имя, шаб in ПРИЗНАКИ:
            if шаб.search(а):
                счёт[имя] += 1
                примеры.setdefault(имя, []).append(а)
                break
for имя, _ in ПРИЗНАКИ:
    if счёт.get(имя):
        print("   %-32s %4d   %s" % (имя, счёт[имя],
                                     ", ".join(примеры[имя][:4])))
print("")
print("=" * 70)
print("=== ЧУЖИЕ АДРЕСА В ПАРТИИ ===")
print("писем всего: %d; подозрительных: %d" % (всего, sum(счёт.values())))
