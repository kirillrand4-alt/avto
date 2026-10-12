# -*- coding: utf-8 -*-
"""Вынуть компании из книги паспортов: идентификатор, адрес письма, роль."""
import json
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

НС = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
АДРЕС = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")
путь, выход = sys.argv[1], sys.argv[2]
ТОЛЬКО = sys.argv[3] if len(sys.argv) > 3 else ""   # имя листа, если нужен один
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
имена = {}
кор = ET.fromstring(z.read("xl/workbook.xml"))
for i, s in enumerate(кор.iter(НС + "sheet"), start=1):
    имена[i] = s.get("name")

вых, видели = [], set()
for лист in sorted((n for n in z.namelist()
                    if re.match(r"xl/worksheets/sheet\d+\.xml$", n)),
                   key=lambda s: int(re.findall(r"\d+", s)[0])):
    номер = int(re.findall(r"\d+", лист)[0])
    имя_листа = имена.get(номер, "")
    if ТОЛЬКО and имя_листа != ТОЛЬКО:
        continue
    if имя_листа in ("Сводка", "Контакты (все)"):
        continue
    шапка = None
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
                и = {н: k for k, н in enumerate(шапка)}
                continue

            def п(имя):
                k = и.get(имя)
                return я[k] if k is not None and k < len(я) else ""

            ид = п("ИНН / УНП")
            if not ид or ид in видели:
                continue
            видели.add(ид)
            почта = п("Письмо: e-mail").lower()
            вых.append({
                "ид": ид, "почта": почта if АДРЕС.match(почта) else "",
                "stupen": п("Письмо: ступень лесенки"),
                "name": п("Название"), "napravlenie": п("Направление"),
                "strana": п("Страна"), "sayt": п("Сайт"),
                "vyruchka": "".join(c for c in п("Выручка, руб") if c.isdigit()),
                "okved": п("Основной ОКВЭД"), "v_baze": п("Есть в нашей базе"),
            })
json.dump(вых, open(выход, "w", encoding="utf-8"), ensure_ascii=False)
ц = sum(1 for x in вых if len("".join(c for c in x["ид"] if c.isdigit())) in (10, 12)
        and x["ид"].isdigit())
print("компаний: %d, с российским ИНН: %d, с почтой письма: %d"
      % (len(вых), ц, sum(1 for x in вых if x["почта"])))
