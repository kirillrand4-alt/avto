# -*- coding: utf-8 -*-
"""След серии в письмах: повторяются ли обороты между письмами партии.

Идея взята из приёмки гостевых постов (LENS-GAPS, дыра №1): линзы смотрят
ОДИН текст и принципиально не видят, что вся партия написана одним
конвейером за день. Там это ловят отдельной фазой по серии.

У нас риск выше, а не ниже: статей 24 в день, писем — сотни, и уходят они на
mail.ru и yandex, которые сравнивают письма между собой. Повторяющийся
оборот в трёхстах письмах — это подпись кампании для фильтра, а не вопрос
вкуса.

Считаем механически: пятисловные фразы, встречающиеся более чем в одном
письме. Без моделей и без денег.
"""
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402

N = 5
ПОРОГ_ДОЛИ = 0.05
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

# служебное: подпись, приветствие и обязательные по канону строки повторяются
# ПО ОПРЕДЕЛЕНИЮ и следом кампании не являются
СЛУЖЕБНОЕ = re.compile(
    r'(?i)(добрый день|с уважением|компрессор центр|руспром|инн \d|'
    r'менеджер по продажам|если тема сейчас неактуальна|'
    r'буду признателен за короткий ответ|перенаправьте)')

for камп, имя in ((10, "КЦ"), (11, "Meyer")):
    with store._lock:
        строки = store._conn.execute(
            "SELECT m.id, m.body_rendered FROM messages m "
            "WHERE m.campaign_id=? AND m.status='sent' "
            "AND m.body_rendered IS NOT NULL "
            "ORDER BY m.sent_at DESC LIMIT 400", (камп,)).fetchall()
    тексты = []
    for r in строки:
        t = re.sub(r"<[^>]+>", " ", str(r["body_rendered"] or ""))
        t = re.sub(r"[^а-яёa-z0-9 ]+", " ", t.lower())
        тексты.append(re.sub(r"\s+", " ", t).strip())
    if len(тексты) < 20:
        print(f"\n== {имя}: писем мало ({len(тексты)}), пропускаю")
        continue
    счёт = Counter()
    for t in тексты:
        слова = t.split()
        свои = {" ".join(слова[i:i + N]) for i in range(len(слова) - N + 1)}
        for ф in свои:
            if not СЛУЖЕБНОЕ.search(ф):
                счёт[ф] += 1
    порог = max(2, int(len(тексты) * ПОРОГ_ДОЛИ))
    частые = [(ф, n) for ф, n in счёт.items() if n >= порог]
    частые.sort(key=lambda t: -t[1])
    print(f"\n== {имя}: писем {len(тексты)}, порог {порог} "
          f"({ПОРОГ_ДОЛИ*100:.0f}%) ==")
    print(f"  пятисловных фраз, повторяющихся выше порога: {len(частые)}")
    for ф, n in частые[:14]:
        print(f"    {n:>4} ({n/len(тексты)*100:>4.1f}%)  «{ф}»")
