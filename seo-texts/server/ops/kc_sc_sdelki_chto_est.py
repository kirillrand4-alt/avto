# -*- coding: utf-8 -*-
"""Владелец 18.11: «что у нас есть по этим сделкам?» — сделки Битрикса (BITRIX-DEAL-20260828.zip) по компаниям из
kc_sc_rassylka.csv: сколько нашлось, какие воронки/стадии, какие поля заполнены (название, товары, сумма, комментарии).
Печатает шапку выгрузки и 8 примеров успешных сделок СЦ. Только чтение.
    kc_sc_sdelki_chto_est.py [--shapka]"""
import csv, html, io, re, sys, zipfile
from collections import Counter, defaultdict
ц = lambda x: "".join(c for c in str(x or "") if c.isdigit())
ИНН = {ц(р["ИНН"]) for р in csv.DictReader(io.open(r"C:\seostat\drop\drop-storage\kc_sc_rassylka.csv", encoding="utf-8-sig"), delimiter=";")} - {""}
ИМЕНА = {(р["Название компании"] or "").strip().lower() for р in csv.DictReader(io.open(r"C:\seostat\drop\drop-storage\kc_sc_rassylka.csv", encoding="utf-8-sig"), delimiter=";")}
z = zipfile.ZipFile(r"C:\seostat\drop\drop-storage\BITRIX-DEAL-20260828.zip")
имя = [i.filename for i in z.infolist() if i.filename.lower().endswith(".xls")][0]
т = z.read(имя).decode("utf-8", "replace")
ряды = re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", т)
яч = lambda р: [html.unescape(re.sub(r"<[^>]+>", " ", x)).strip() for x in re.findall(r"(?is)<t[hd][^>]*>(.*?)</t[hd]>", р)]
шапка = яч(ряды[0])
print("сделок в выгрузке:", len(ряды) - 1, "| колонок:", len(шапка))
if "--shapka" in sys.argv: print(шапка); sys.exit(0)
ик = [i for i, h in enumerate(шапка) if re.search(r"(?i)инн", h)]
ин = [i for i, h in enumerate(шапка) if re.search(r"(?i)^компания$|название компании|компания: название", h)]
нужн = lambda *вар: next((i for i, h in enumerate(шапка) for в in вар if re.search(в, h, re.I)), None)
К = {"воронка": нужн(r"^воронка", r"направлен"), "стадия": нужн(r"^стадия"), "название": нужн(r"^название сделки", r"^название$"),
     "сумма": нужн(r"^сумма"), "товары": нужн(r"товар", r"продукт"), "комментарий": нужн(r"^комментар"), "создана": нужн(r"дата создания", r"^создан"),
     "закрыта": нужн(r"дата закрыт", r"предполагаем")}
print("колонки:", {к: (шапка[i] if i is not None else None) for к, i in К.items()}, "| ИНН-колонки:", [шапка[i] for i in ик])
по = defaultdict(list)
for р in ряды[1:]:
    v = яч(р)
    инн = next((ц(v[i]) for i in ик if i < len(v) and len(ц(v[i])) in (10, 12)), "")
    комп = next((v[i].lower() for i in ин if i < len(v) and v[i]), "")
    if инн in ИНН or (not инн and комп in ИМЕНА): по[инн or комп].append({к: (v[i] if i is not None and i < len(v) else "") for к, i in К.items()})
print("компаний из списка с хоть одной сделкой: %d из %d ИНН" % (len(по), len(ИНН)))
сд = [x for v in по.values() for x in v]
print("сделок у них:", len(сд), "| воронки:", Counter(x["воронка"] for x in сд).most_common(10))
print("стадии:", Counter(x["стадия"] for x in сд).most_common(12))
for к in К: print("   заполнено «%s»: %d" % (к, sum(1 for x in сд if x[к])))
усп = [x for x in сд if re.search(r"(?i)успеш|выигр|оплач|закрыт.*усп|сделка успешна", x["стадия"])]
print("успешных:", len(усп))
import random; random.seed(18)
for x in random.sample(усп or сд, min(8, len(усп or сд))): print("  ", {к: v[:120] for к, v in x.items() if v})
