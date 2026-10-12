# -*- coding: utf-8 -*-
"""Сводка по книге: листы, строки, одинакова ли шапка, ключевые заполнения."""
import json
import re
import sys
import zipfile
from collections import Counter
from xml.etree import ElementTree as ET

НС = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
путь = sys.argv[1]
z = zipfile.ZipFile(путь)
общие = []
if "xl/sharedStrings.xml" in z.namelist():
    with z.open("xl/sharedStrings.xml") as f:
        буф = []
        for _, эл in ET.iterparse(f, events=("end",)):
            if эл.tag == НС + "t":
                буф.append(эл.text or "")
            elif эл.tag == НС + "si":
                общие.append("".join(буф))
                буф = []
                эл.clear()

# имена листов
имена = {}
if "xl/workbook.xml" in z.namelist():
    кор = ET.fromstring(z.read("xl/workbook.xml"))
    for i, s in enumerate(кор.iter(НС + "sheet"), start=1):
        имена[i] = s.get("name")

ИНТЕРЕС = ["Письмо: e-mail", "Письмо: кому (ФИО)", "Письмо: должность",
           "Письмо: ступень лесенки", "ИНН / УНП", "Название", "Сайт",
           "Выручка, руб", "Основной ОКВЭД", "Продукция",
           "Все почты по лесенке (роль, ЛПР, ФИО/должность)",
           "Все телефоны (роль, ЛПР, ФИО/должность)", "Направление"]
итог, шапки = [], Counter()
ступени, направления = Counter(), Counter()
всего_строк = 0
занято_общее = Counter()
for лист in sorted((n for n in z.namelist()
                    if re.match(r"xl/worksheets/sheet\d+\.xml$", n)),
                   key=lambda s: int(re.findall(r"\d+", s)[0])):
    номер = int(re.findall(r"\d+", лист)[0])
    шапка, строк = None, 0
    занято = Counter()
    with z.open(лист) as f:
        for _, эл in ET.iterparse(f, events=("end",)):
            if эл.tag != НС + "row":
                continue
            я = []
            for c in эл.findall(НС + "c"):
                v, из, т = c.find(НС + "v"), c.find(НС + "is"), c.get("t")
                if из is not None:
                    з = "".join(x.text or "" for x in из.iter(НС + "t"))
                elif v is None:
                    з = ""
                else:
                    з = v.text or ""
                    if т == "s" and з.isdigit() and int(з) < len(общие):
                        з = общие[int(з)]
                я.append(str(з).strip())
            эл.clear()
            if шапка is None:
                шапка = я
                continue
            строк += 1
            for i, имя in enumerate(шапка):
                if i < len(я) and я[i]:
                    занято[имя] += 1
                    занято_общее[имя] += 1
            д = {имя: (я[i] if i < len(я) else "")
                 for i, имя in enumerate(шапка)}
            if д.get("Письмо: ступень лесенки"):
                ступени[д["Письмо: ступень лесенки"]] += 1
            if д.get("Направление"):
                направления[д["Направление"]] += 1
    if not шапка:
        continue
    шапки[tuple(шапка)] += 1
    всего_строк += строк
    итог.append((имена.get(номер, лист), строк, len(шапка)))

print("листов: %d, строк всего: %d, разных шапок: %d"
      % (len(итог), всего_строк, len(шапки)))
print("")
print("--- листы ---")
for имя, строк, кол in итог:
    print("   %-44s строк %5d, колонок %d" % (str(имя)[:44], строк, кол))
print("")
print("--- заполненность ключевых колонок по всей книге ---")
for имя in ИНТЕРЕС:
    if имя in занято_общее:
        print("   %-50s %6d  (%.0f%%)"
              % (имя[:50], занято_общее[имя],
                 100.0 * занято_общее[имя] / всего_строк if всего_строк else 0))
print("")
print("--- ступени лесенки, по которым выбран адрес письма ---")
for к, n in ступени.most_common(20):
    print("   %-36s %6d" % (к[:36], n))
if направления:
    print("")
    print("--- направления ---")
    for к, n in направления.most_common(20):
        print("   %-44s %6d" % (к[:44], n))
