# -*- coding: utf-8 -*-
"""Только чтение: какие финальные вопросы наших писем дают ответы."""
import re
import sqlite3
from collections import defaultdict

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

ушли = list(c.execute(
    "SELECT m.id, m.recipient_id, m.campaign_id, m.body_rendered b"
    " FROM messages m WHERE m.status='sent' AND m.body_rendered<>''"))
print("отправленных писем с сохранённым текстом: %d" % len(ушли))

ответили = set()
for р in c.execute("SELECT recipient_id, event_type FROM events"
                   " WHERE event_type IN ('reply','reply_auto')"):
    ответили.add((р["recipient_id"], р["event_type"]))
живые = {r for r, t in ответили if t == "reply"}
любые = {r for r, _ in ответили}
print("получателей с живым ответом: %d, с любым (вкл. авто): %d"
      % (len(живые), len(любые)))


def финал(тело):
    """Последнее предложение с вопросительным знаком."""
    т = тело.split("С уважением")[0]
    вопр = re.findall(r"[^.!?\n]*\?", т)
    return вопр[-1].strip() if вопр else ""


def тип(в):
    н = в.lower()
    if not в:
        return "без вопроса"
    if "актуальн" in н:
        return "актуально ли (да/нет про интерес)"
    if "есть ли" in н or "стоит ли" in н:
        return "есть ли задача (да/нет про факт)"
    if "как" in н and ("сейчас" in н or "чем" in н):
        return "как/чем сейчас (открытый про факт)"
    if "подскажите" in н or "скажите" in н:
        return "прочее с «подскажите»"
    if "удобно" in н or "созвон" in н or "встреч" in н or "звонк" in н:
        return "предложение созвона"
    if "прислать" in н or "выслать" in н or "отправить" in н:
        return "предложение прислать материалы"
    return "прочее"


ст = defaultdict(lambda: [0, 0, 0])
for р in ушли:
    к = тип(финал(р["b"] or ""))
    ст[к][0] += 1
    if р["recipient_id"] in живые:
        ст[к][1] += 1
    if р["recipient_id"] in любые:
        ст[к][2] += 1

print("\n=== ОТВЕТЫ ПО ТИПУ ФИНАЛЬНОГО ВОПРОСА ===")
print("  %-40s %6s %7s %7s" % ("тип", "писем", "ответ", "доля"))
for к, (n, ж, л) in sorted(ст.items(), key=lambda x: -x[1][0]):
    if n < 15:
        continue
    print("  %-40s %6d %7d %6.1f%%" % (к[:40], n, ж, 100.0 * ж / n))

print("\n=== ЧАСТЫЕ ФОРМУЛИРОВКИ И ИХ ОТДАЧА ===")
ф = defaultdict(lambda: [0, 0])
for р in ушли:
    в = финал(р["b"] or "")
    if len(в) < 12:
        continue
    ключ = re.sub(r"\s+", " ", в)[:70]
    ф[ключ][0] += 1
    if р["recipient_id"] in живые:
        ф[ключ][1] += 1
топ = sorted((x for x in ф.items() if x[1][0] >= 25), key=lambda x: -x[1][1] / x[1][0])
for к, (n, ж) in топ[:10]:
    print("  %5.1f%% (%3d/%4d)  %s" % (100.0 * ж / n, ж, n, к))
print("  ...")
for к, (n, ж) in топ[-5:]:
    print("  %5.1f%% (%3d/%4d)  %s" % (100.0 * ж / n, ж, n, к))
