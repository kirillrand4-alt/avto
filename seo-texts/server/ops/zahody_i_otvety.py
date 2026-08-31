# -*- coding: utf-8 -*-
"""Какие заходы КЦ собрали ответы ЖИВЫХ людей.

Живой ответ — events.event_type='reply'. Автоответы ('reply_auto'), отбивки
('bounce'), служебные отчёты почтовиков ('otchet') и прочее сюда не идут.

Заход считаем тем же классификатором, что и антиштамп в бою —
ai_letter.форма_захода по первой содержательной строке письма.

Доверительный интервал — Уилсон, однородность — хи-квадрат вручную (scipy на
сервере нет).
"""
import io
import json
import math
import os
import sqlite3
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import форма_захода                     # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\zahody-otvety.jsonl"
МЕЙЕР = {7, 8, 11}
ТЕСТЫ = {2, 3, 4}

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=90)
c.row_factory = sqlite3.Row

print("=== ОТПРАВЛЕНО ПО КАМПАНИЯМ ===")
кц_камп = []
for r in c.execute("SELECT m.campaign_id k, COALESCE(c2.name,'') n, COUNT(*) x"
                   "  FROM messages m LEFT JOIN campaigns c2 ON c2.id=m.campaign_id"
                   " WHERE m.sent_at IS NOT NULL GROUP BY m.campaign_id"
                   " ORDER BY x DESC"):
    метка = "Meyer" if r["k"] in МЕЙЕР else ("тест" if r["k"] in ТЕСТЫ else "КЦ")
    if метка == "КЦ":
        кц_камп.append(r["k"])
    print("   %-4s %-32s %6d  %s" % (r["k"], r["n"][:32], r["x"], метка))

письма = {}
for r in c.execute("SELECT id, recipient_id, campaign_id, body_rendered, sent_at"
                   "  FROM messages WHERE sent_at IS NOT NULL"
                   "   AND campaign_id IN (%s)" % ",".join("?" * len(кц_камп)),
                   кц_камп):
    if not r["body_rendered"]:
        continue
    письма[r["id"]] = {"rid": r["recipient_id"], "camp": r["campaign_id"],
                       "zahod": форма_захода(r["body_rendered"]),
                       "sent": r["sent_at"]}
print("\nписем КЦ с телом: %d" % len(письма))

# письма получателя по времени — чтобы привязать ответ без message_id
по_получателю = defaultdict(list)
for mid, п in письма.items():
    по_получателю[п["rid"]].append((str(п["sent"] or ""), mid))
for v in по_получателю.values():
    v.sort()

ответившие = {}          # mid -> сколько живых ответов
живых_всего, без_привязки = 0, 0
for r in c.execute("SELECT recipient_id, message_id, event_ts FROM events"
                   " WHERE event_type='reply'"):
    живых_всего += 1
    mid = r["message_id"]
    if mid not in письма:
        mid = None
        свои = по_получателю.get(r["recipient_id"]) or []
        когда = str(r["event_ts"] or "")
        раньше = [м for т, м in свои if not когда or т <= когда]
        if раньше:
            mid = раньше[-1]
        elif свои:
            mid = свои[-1][1]
    if mid is None:
        без_привязки += 1
        continue
    ответившие[mid] = ответившие.get(mid, 0) + 1
c.close()
print("живых ответов всего в базе: %d; привязано к письмам КЦ: %d; "
      "не привязано (Meyer/тесты/нет письма): %d"
      % (живых_всего, len(ответившие), без_привязки))


def уилсон(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / float(n)
    д = 1 + z * z / n
    ц = (p + z * z / (2 * n)) / д
    р = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / д
    return (max(0.0, ц - р) * 100, min(1.0, ц + р) * 100)


def гамма_p(хи2, df):
    """p-value хи-квадрата через ряд для неполной гамма-функции."""
    if хи2 <= 0 or df <= 0:
        return 1.0
    x, a = хи2 / 2.0, df / 2.0
    # регуляризованная нижняя неполная гамма через ряд
    сум, член = 1.0 / a, 1.0 / a
    for n in range(1, 400):
        член *= x / (a + n)
        сум += член
        if член < сум * 1e-12:
            break
    lg = math.lgamma(a)
    P = сум * math.exp(-x + a * math.log(x) - lg)
    return max(0.0, min(1.0, 1.0 - P))


счёт = Counter()
ответы = Counter()
for mid, п in письма.items():
    z = п["zahod"] or "(нет первой строки)"
    счёт[z] += 1
    if mid in ответившие:
        ответы[z] += 1

ИМЕНОВАННЫЕ = {"от профиля", "от вопроса", "от условия", "от отрасли",
               "от площадки"}
крупные = [z for z in счёт if счёт[z] >= 100]
строки = []
for z in счёт:
    группа = z if (z in ИМЕНОВАННЫЕ or z in крупные) else "(хвост редких форм)"
    строки.append((группа, счёт[z], ответы[z]))
свод = defaultdict(lambda: [0, 0])
for г, n, k in строки:
    свод[г][0] += n
    свод[г][1] += k

итог = sorted(свод.items(), key=lambda п: -п[1][1])
with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
    f.write(json.dumps({"ts": int(time.time()),
                        "svod": {г: v for г, v in свод.items()}},
                       ensure_ascii=False) + "\n")
    f.flush()
    os.fsync(f.fileno())

вн = sum(v[1] for v in свод.values())
вс = sum(v[0] for v in свод.values())
хи2 = 0.0
df = 0
общая = вн / float(вс) if вс else 0
for г, (n, k) in свод.items():
    if n < 30:
        continue
    ож = n * общая
    if ож <= 0:
        continue
    хи2 += (k - ож) ** 2 / ож + ((n - k) - (n - ож)) ** 2 / max(1e-9, n - ож)
    df += 1
df = max(0, df - 1)

print("\n=== ЗАХОДЫ КЦ И ЖИВЫЕ ОТВЕТЫ ===")
print("   %-24s %7s %8s %8s %s" % ("заход", "писем", "ответов", "доля", "95% интервал"))
for г, (n, k) in итог:
    низ, верх = уилсон(k, n)
    print("   %-24s %7d %8d %7.2f%%  %.2f–%.2f%%"
          % (г, n, k, 100.0 * k / n if n else 0, низ, верх))

print("\n=== ИТОГ ===")
print("всего писем КЦ: %d, живых ответов: %d, общая доля %.2f%%"
      % (вс, вн, 100.0 * общая))
print("хи-квадрат однородности по формам с n>=30: %.2f при df=%d, p=%.3f"
      % (хи2, df, гамма_p(хи2, df)))
print("вывод: %s" % ("различия между заходами статистически значимы"
                     if гамма_p(хи2, df) < 0.05 else
                     "различия НЕ значимы — это разброс, а не эффект захода"))
