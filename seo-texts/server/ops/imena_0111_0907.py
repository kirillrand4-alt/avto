# -*- coding: utf-8 -*-
"""Только чтение: годится ли название компании 01.11 для подстановки в письмо."""
import re
import sqlite3

e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
o = sqlite3.connect("file:C:/sender/obzvon-index.db?mode=ro", uri=True)
o.row_factory = sqlite3.Row
мейер = {р["inn"] for р in o.execute(
    "SELECT inn FROM obzvon WHERE division LIKE '%meyer%'")}

ФОРМЫ = r"^(ООО|ОАО|АО|ЗАО|ПАО|НАО|СПК|СХПК|ПК|КФХ|К/Х|ИП|ТНВ|ГУП|МУП|ФГУП|" \
        r"СЕЛЬСКОХОЗЯЙСТВЕННЫЙ ПРОИЗВОДСТВЕННЫЙ КООПЕРАТИВ|" \
        r"КРЕСТЬЯНСКОЕ \(ФЕРМЕРСКОЕ\) ХОЗЯЙСТВО|КРЕСТЬЯНСКО-ФЕРМЕРСКОЕ ХОЗЯЙСТВО)\b"


def разобрать(имя):
    """Возвращает (тип, короткое название)."""
    s = re.sub(r"\s+", " ", (имя or "").strip())
    в_кавычках = re.findall(r"[«\"']([^«»\"']{2,})[»\"']", s)
    голое = re.sub(ФОРМЫ, "", s.upper()).strip(' "«»')
    if в_кавычках:
        к = в_кавычках[0].strip()
        # «Иванов И.И.» в кавычках это всё равно фамилия
        if re.match(r"^[А-ЯЁ][а-яё]+( [А-ЯЁ]\.\s?[А-ЯЁ]\.)$", к):
            return "фамилия", к
        return "название", к
    if re.match(r"^(ИП|ГЛАВА)", s.upper()):
        return "ип", голое
    # ФИО без кавычек: три слова с заглавных или Фамилия И.И.
    if re.match(r"^[А-ЯЁ][А-ЯЁа-яё-]+ [А-ЯЁ][а-яё]*\.?\s?[А-ЯЁ][а-яё]*\.?$", голое):
        return "фамилия", голое
    if голое:
        return "без кавычек", голое
    return "пусто", ""


print("=== КАКИЕ КОДЫ 01.* ЕСТЬ В БАЗЕ ===")
for р in e.execute("SELECT substr(okved,1,5) k, count(*) n FROM companies"
                   " WHERE okved LIKE '01.%' GROUP BY k ORDER BY n DESC LIMIT 12"):
    print("   %-7s %6d" % (р["k"], р["n"]))

ряды = [р for р in e.execute(
    "SELECT inn, name, revenue_rub, site, activity FROM companies"
    " WHERE okved LIKE '01.%'")]
голые = [р for р in ряды
         if not (р["site"] or "").strip()
         and len((р["activity"] or "").strip()) < 15]
цель = [р for р in голые
        if р["inn"] in мейер and (р["revenue_rub"] or 0) >= 30_000_000]

for метка, набор in (("ВСЕ 01.* (растениеводство и животноводство)", ряды), ("ТОЛЬКО ОКВЭД", голые),
                     ("ЦЕЛЬ: meyer + 30млн+", цель)):
    счёт = {}
    for р in набор:
        т, _ = разобрать(р["name"])
        счёт[т] = счёт.get(т, 0) + 1
    итого = len(набор) or 1
    print("\n=== %s: %d ===" % (метка, len(набор)))
    for т, n in sorted(счёт.items(), key=lambda x: -x[1]):
        print("   %-12s %6d  %5.1f%%" % (т, n, 100.0 * n / итого))

print("\n=== ПРИМЕРЫ ИЗ ЦЕЛЕВОГО СПИСКА (что подставится в письмо) ===")
показано = {}
for р in sorted(цель, key=lambda x: -(x["revenue_rub"] or 0)):
    т, к = разобрать(р["name"])
    if показано.get(т, 0) >= 5:
        continue
    показано[т] = показано.get(т, 0) + 1
    print("   %-12s | %-38s | -> «%s»" % (т, str(р["name"])[:38], к))
