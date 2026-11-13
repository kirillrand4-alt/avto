# -*- coding: utf-8 -*-
"""Причины провала (drop meyer-kontakty-prichiny.csv: ПРОДАЖА_ПРИЧИНА, ПРИВЛЕЧЕНИЕ_ПРИЧИНА) по подходящим компаниям
meyer-provaly2.jsonl (не стоп): раскладка на шаблоны редактора. Только чтение.
 Продажа (структурное поле): «купили у конкурентов*» → конкуренты; «отложили…» и «не выходит на связь» → отложили;
 «отпала потребность/ФТС не нужен» → задач не было; дубль/не наш/банкротство/спам — не писать.
 Привлечение (свободный текст) — считаем грубо по словам; точно разложит модель."""
import csv, io, json, re
from collections import Counter, defaultdict
csv.field_size_limit(10 ** 9)
пп, пр = {}, {}
for р in csv.DictReader(io.open(r"C:\seostat\drop\drop-storage\meyer-kontakty-prichiny.csv", encoding="utf-8-sig", errors="replace"), delimiter=";"):
    d = р["DEAL_ID"].strip()
    if (р.get("ПРОДАЖА_ПРИЧИНА") or "").strip(): пп[d] = р["ПРОДАЖА_ПРИЧИНА"].strip()
    if (р.get("ПРИВЛЕЧЕНИЕ_ПРИЧИНА") or "").strip(): пр[d] = р["ПРИВЛЕЧЕНИЕ_ПРИЧИНА"].strip()
def шаблон_прод(т):
    т = т.lower()
    if "купили" in т: return "конкуренты"
    if "отложили" in т or "не выходит на связь" in т: return "отложили"
    if "отпала потребность" in т or "фтс не нужен" in т or "нету фтс" in т: return "задач не было"
    if re.search(r"дубль|не наш|банкрот|спам|нецелев|ведеться работа", т): return "НЕ ПИСАТЬ"
    return "?"
def шаблон_прив(т):
    т = т.lower()
    if re.search(r"купил|стоит .*сепаратор|есть фтс|уже есть|работают с|конкурент", т): return "конкуренты"
    if re.search(r"не выход|не отвеч|не берут|не дозвон|отлож|позже|осенью|весной|летом|в следующ|на следующ|нет бюджет|перезвон", т): return "отложили"
    if re.search(r"дубль|не наш|банкрот|ликвид|спам|не существ", т): return "НЕ ПИСАТЬ"
    if re.search(r"не надо|не нуж|не интерес|не актуал|нет потреб|не предвид|не требует|не планир|интереса нет", т): return "задач не было"
    return "? (модель)"
сч = Counter(); прим = defaultdict(list)
for с in io.open(r"C:\sender\_ops\meyer-provaly2.jsonl", encoding="utf-8"):
    x = json.loads(с)
    if x.get("stop"): continue
    кат = [шаблон_прод(пп[d]) for d in x["sdelki"] if d in пп]
    if кат: к = "Продажа: " + Counter(кат).most_common(1)[0][0]
    else:
        кп = [шаблон_прив(пр[d]) for d in x["sdelki"] if d in пр]
        к = ("Привлечение: " + Counter(кп).most_common(1)[0][0]) if кп else "причины нет"
    сч[к] += 1
    if len(прим[к]) < 3 and not к.startswith("Продажа"): прим[к] += [пр[d][:90] for d in x["sdelki"] if d in пр][:1]
print("подходящих компаний по шаблонам:")
for к, v in сч.most_common(): print("  %-40s %d   %s" % (к, v, прим.get(к, "")))
