# -*- coding: utf-8 -*-
"""Хвост форм и группировка заходов по смыслу, а не по первым двум словам."""
import math
import re
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import форма_захода, _первая_фраза      # noqa: E402

МЕЙЕР, ТЕСТЫ = {7, 8, 11}, {2, 3, 4}
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=90)
c.row_factory = sqlite3.Row
письма = {}
for r in c.execute("SELECT id, recipient_id, body_rendered, sent_at, campaign_id"
                   "  FROM messages WHERE sent_at IS NOT NULL"):
    if r["campaign_id"] in МЕЙЕР or r["campaign_id"] in ТЕСТЫ:
        continue
    if not r["body_rendered"]:
        continue
    письма[r["id"]] = {"rid": r["recipient_id"],
                       "первая": _первая_фраза(r["body_rendered"]),
                       "форма": форма_захода(r["body_rendered"]),
                       "sent": str(r["sent_at"] or "")}
по_получателю = defaultdict(list)
for mid, п in письма.items():
    по_получателю[п["rid"]].append((п["sent"], mid))
for v in по_получателю.values():
    v.sort()
ответившие = set()
for r in c.execute("SELECT recipient_id, message_id, event_ts FROM events"
                   " WHERE event_type='reply'"):
    mid = r["message_id"] if r["message_id"] in письма else None
    if mid is None:
        свои = по_получателю.get(r["recipient_id"]) or []
        когда = str(r["event_ts"] or "")
        раньше = [м for т, м in свои if not когда or т <= когда]
        mid = раньше[-1] if раньше else (свои[-1][1] if свои else None)
    if mid is not None:
        ответившие.add(mid)
c.close()

ИМЕНОВАННЫЕ = {"от профиля", "от вопроса", "от условия", "от отрасли",
               "от площадки"}
хвост = Counter()
хвост_отв = Counter()
for mid, п in письма.items():
    ф = п["форма"] or "(пусто)"
    if ф in ИМЕНОВАННЫЕ:
        continue
    хвост[ф] += 1
    if mid in ответившие:
        хвост_отв[ф] += 1
print("=== ХВОСТ: 24 самые частые неопознанные формы ===")
print("   %-26s %6s %7s" % ("первые два слова", "писем", "ответов"))
for ф, n in хвост.most_common(24):
    print("   %-26s %6d %7d" % (ф, n, хвост_отв[ф]))
print("   всего в хвосте: %d форм, %d писем, %d ответов"
      % (len(хвост), sum(хвост.values()), sum(хвост_отв.values())))

# --- семейства по смыслу первой фразы ---------------------------------------
СЕМЬИ = (
    ("наблюдение о них", r'^\W*((по)?смотрел|изучил|глянул|видел|ознакомил|'
                         r'знакомил|прочитал|прошёлся|прошелся|разбирал|'
                         r'просмотрел|заглянул|полистал|нашёл|нашел|'
                         r'обратил внимание|судя по|профиль ваш|у вас на сайте)'),
    ("представление себя", r'^\W*(я\s|меня зовут|веду направлен)'),
    ("от площадки", r'^\W*(на|в|при|у)\s'),
    ("от отрасли", r'^\W*(производств|обработк|изготовлен|компани|предприяти|'
                   r'завод|цех|линия|комбинат)'),
    ("от вопроса", r'^\W*(подскажите|скажите|вопрос|интересно)'),
    ("от условия", r'^\W*(если|когда|пока)\s'),
    ("от новости", r'(?i)(новост|сообщал|писали, что|анонс)'),
    ("про снабжение/замену", r'(?i)^\W*(вам как снабжен|замен|аналог)'),
)


def семья(первая):
    for имя, rx in СЕМЬИ:
        if re.search("(?i)" + rx, первая or ""):
            return имя
    return "прочее"


счёт, отв = Counter(), Counter()
for mid, п in письма.items():
    с = семья(п["первая"])
    счёт[с] += 1
    if mid in ответившие:
        отв[с] += 1


def уилсон(k, n, z=1.96):
    if not n:
        return (0.0, 0.0)
    p = k / float(n)
    д = 1 + z * z / n
    ц = (p + z * z / (2 * n)) / д
    р = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / д
    return (max(0.0, ц - р) * 100, min(1.0, ц + р) * 100)


def гамма_p(хи2, df):
    if хи2 <= 0 or df <= 0:
        return 1.0
    x, a = хи2 / 2.0, df / 2.0
    сум, член = 1.0 / a, 1.0 / a
    for n in range(1, 400):
        член *= x / (a + n)
        сум += член
        if член < сум * 1e-12:
            break
    P = сум * math.exp(-x + a * math.log(x) - math.lgamma(a))
    return max(0.0, min(1.0, 1.0 - P))


вс, вн = sum(счёт.values()), sum(отв.values())
общая = вн / float(вс)
хи2, df = 0.0, 0
for с, n in счёт.items():
    if n < 50:
        continue
    k, ож = отв[с], n * общая
    хи2 += (k - ож) ** 2 / ож + ((n - k) - (n - ож)) ** 2 / (n - ож)
    df += 1
df = max(0, df - 1)
p = гамма_p(хи2, df)

print("\n=== ЗАХОДЫ, СГРУППИРОВАННЫЕ ПО СМЫСЛУ ===")
print("   %-22s %7s %8s %8s   %s" % ("семейство", "писем", "ответов", "доля",
                                     "95% интервал"))
for с, n in sorted(счёт.items(), key=lambda x: -отв[x[0]]):
    низ, верх = уилсон(отв[с], n)
    print("   %-22s %7d %8d %7.2f%%   %.2f–%.2f%%"
          % (с, n, отв[с], 100.0 * отв[с] / n, низ, верх))

print("\n=== ИТОГ ===")
print("писем КЦ %d, живых ответов %d, общая доля %.2f%%" % (вс, вн, 100 * общая))
print("хи-квадрат по семействам с n>=50: %.2f, df=%d, p=%.3f" % (хи2, df, p))
print("чтобы поймать разницу в 1 п.п. при базе 2.4%%, на каждый заход нужно")
print("примерно 3500-4000 писем — сейчас столько есть только у одного.")
print("вывод: %s" % ("различия значимы" if p < 0.05 else
                     "различия в пределах разброса; лидер по ЧИСЛУ ответов — "
                     "просто самый частый заход"))
