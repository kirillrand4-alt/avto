# -*- coding: utf-8 -*-
"""Механическая проверка всех разобранных названий партии.

Тридцать писем глазами не покрывают 2 665 названий: редкая поломка сидит
в хвосте. Здесь ищем следы, по которым видно неудачный разбор, и печатаем
только подозрительные - их и смотрим глазами.
"""
import io, json, os, re, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from imya_v_pismo import итоговое_имя                          # noqa: E402

ИМЕНА = r"C:\sender\_ops\agro-imena.jsonl"
ФОРМЫ = re.compile(r"(?i)\b(ООО|ОАО|ЗАО|ПАО|АО|СПК|СХПК|КФХ|К/Х|КХ|ТНВ|НАО|"
                   r"общество с ограниченной|акционерное общество|"
                   r"крестьянское \(фермерское\))\b")
КАВЫЧКИ = re.compile(r'["«»„“”]')
ЛАТИНИЦА = re.compile(r"[A-Za-z]")
ГЛАСНЫЕ = set("АЕЁИОУЫЭЮЯ")

имена = {}
for с in io.open(ИМЕНА, encoding="utf-8", errors="replace"):
    с = с.strip()
    if not с:
        continue
    try:
        z = json.loads(с)
    except Exception:                                          # noqa: BLE001
        continue
    if z.get("сыро"):
        имена[z["сыро"]] = z

флаги = Counter()
плохие = []
хозяйств = 0
for сыро, z in sorted(имена.items()):
    # ПРОВЕРЯЕМ ТО, ЧТО РЕАЛЬНО УЙДЁТ В ПИСЬМО, а не промежуточный разбор:
    # внутренние кавычки и длинные ФИО снимает уже itogovoe_imya.
    подл, вид = итоговое_имя(z.get("имя"), bool(z.get("человек")))
    if вид == "хозяйство":
        хозяйств += 1
        continue
    имя = подл.strip("«»")
    п = []
    if not имя.strip():
        п.append("пусто")
    if КАВЫЧКИ.search(имя):
        п.append("кавычки внутри")
    if ФОРМЫ.search(имя):
        п.append("осталась юрформа")
    if ЛАТИНИЦА.search(имя):
        п.append("латиница")
    if len(имя) > 45:
        п.append("длинное")
    if len(имя.replace(" ", "")) < 3:
        п.append("короче трёх букв")
    ядро = "".join(c for c in имя if c.isalpha())
    if ядро and ядро.upper() == ядро and len(ядро) > 4 and (set(ядро) & ГЛАСНЫЕ):
        п.append("всё прописными")
    if имя.strip() == сыро.strip():
        п.append("разбор ничего не сделал")
    if re.search(r"\s{2,}|^\s|\s$", имя):
        п.append("лишние пробелы")
    if not z.get("человек") and re.search(r"[А-ЯЁ]\.\s*[А-ЯЁ]\.", имя):
        п.append("инициалы, но не помечено человеком")
    if п:
        плохие.append((сыро, имя, bool(z.get("человек")), п))
        for к in п:
            флаги[к] += 1

for сыро, имя, чел, п in плохие[:60]:
    print("   %-38s → %-32s %s%s"
          % (сыро[:38], имя[:32], ", ".join(п), "  [человек]" if чел else ""))
print("")
print("=" * 78)
print("=== ПРОВЕРКА НАЗВАНИЙ ===")
print("разобрано названий: %d; из них «Ваше хозяйство»: %d; "
      "с замечаниями: %d" % (len(имена), хозяйств, len(плохие)))
for к, в in флаги.most_common():
    print("   %-38s %5d" % (к, в))
