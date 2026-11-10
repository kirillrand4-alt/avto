# -*- coding: utf-8 -*-
"""Выгрузка сделок Битрикса (BITRIX-DEAL-*.zip, HTML-xls): какие колонки есть про стадию/воронку/причину
провала, и свод причин провала по воронкам Meyer. Только чтение.
    bitrix_sdelki_prichiny.py [--kolonki]"""
import html, io, re, sys, zipfile
from collections import Counter
z = zipfile.ZipFile(r"C:\seostat\drop\drop-storage\BITRIX-DEAL-20260828.zip")
имя = [i.filename for i in z.infolist() if i.filename.lower().endswith(".xls")][0]
т = z.read(имя).decode("utf-8", "replace")
ряды = re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", т)
яч = lambda р: [html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"(?is)<t[hd][^>]*>(.*?)</t[hd]>", р)]
шапка = яч(ряды[0]); print("сделок:", len(ряды) - 1, "колонок:", len(шапка))
КЛ = re.compile(r"(?i)причин|провал|отказ|проигр|стади|воронк|направлен|закрыт|комментар|итог|результат")
кол = [(i, h) for i, h in enumerate(шапка) if КЛ.search(h) and not h.startswith("Компания:") and not h.startswith("Контакт:")]
print("колонки про стадию/причину:", [h for _, h in кол])
if "--kolonki" in sys.argv: sys.exit(0)
ид = {h: i for i, h in enumerate(шапка)}
def col(*вар):
    for в in вар:
        for h, i in ид.items():
            if h.lower() == в.lower(): return i
    for в in вар:
        for h, i in ид.items():
            if в.lower() in h.lower() and not h.startswith(("Компания:", "Контакт:")): return i
ВОР, СТ = col("Воронка", "Направление"), col("Стадия сделки", "Стадия")
причины = [i for i, h in кол if re.search(r"(?i)причин|провал|отказ|проигр", h)]
print("воронка:", шапка[ВОР] if ВОР is not None else None, "| стадия:", шапка[СТ] if СТ is not None else None, "| поля причины:", [шапка[i] for i in причины])
вор, стадии, сч = Counter(), Counter(), {i: Counter() for i in причины}
все_вор = Counter(яч(р)[ВОР] if ВОР < len(яч(р)) else "?" for р in ряды[1:])
print("значения «Воронка» (все сделки):", все_вор.most_common(15))
for р in ряды[1:]:
    в = яч(р)
    if ВОР is None or ВОР >= len(в): continue
    if "meyer" not in в[ВОР].lower(): continue
    вор[в[ВОР]] += 1
    ст = в[СТ] if СТ is not None and СТ < len(в) else ""
    стадии[ст] += 1
    if re.search(r"(?i)провал|отказ|проигр|не реализ|закрыта неуспешно|неуспеш", ст):
        for i in причины:
            if i < len(в): сч[i][(в[i] or "(пусто)")[:80]] += 1
print("воронки Meyer:", вор.most_common())
print("стадии Meyer:", стадии.most_common(15))
for i in причины: print("== причины в «%s»:" % шапка[i]); [print("   %5d  %s" % (n, k)) for k, n in сч[i].most_common(20)]
