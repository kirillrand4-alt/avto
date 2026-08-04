# -*- coding: utf-8 -*-
"""Пересчёт того, что видно глазами в карточках: сколько таких по всей базе.

ПОВОД. Открыла карточки панели и увидела три вещи, каждую из которых поодиночке можно
списать на случайность:
  * в «Источниках проверки компании» стоит `ZHURNAL-2 (ветка claude read-intro-section-...)`
    — имя ветки чужого журнала как доказательство про компанию;
  * один и тот же факт показан ДВАЖДЫ: заключение ЭПБ № 68-ТУ-05539-2024 с одинаковой
    цитатой идёт и как «тип не установлен», и как «центробежная»;
  * у Ставрополькрайводоканала в цитате прямо «турбокомпрессора ВОЗДУШНОГО многоступенчатого»,
    а в строке «Рабочая среда: не названа».
Прежде чем называть это дефектом панели, считаю, сколько таких по всей базе. Один случай —
случайность, тысяча — правило.
"""
import json
import re
import sqlite3

cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
o = {}

# 1. Мусор в источниках. Признак: источник похож на имя файла журнала или ветки, а не на
# площадку. Ссылки при этом нет — проверить нечем.
MUSOR = "lower(coalesce(source,'')) like '%zhurnal%' or lower(coalesce(source,'')) like '%ветка%' " \
        "or lower(coalesce(source,'')) like '%claude%' or lower(coalesce(source,'')) like '%.md%'"
o['фактов_с_мусорным_источником'] = cx.execute(
    f'select count(*) from fact where {MUSOR}').fetchone()[0]
o['компаний_с_таким_источником'] = cx.execute(
    f'select count(distinct inn) from fact where {MUSOR}').fetchone()[0]
o['примеры_источников'] = cx.execute(
    f'select coalesce(source,\'\'), count(*) from fact where {MUSOR} group by 1 '
    f'order by 2 desc limit 6').fetchall()

# 2. Двойники: одна и та же цитата у одного ИНН, но разный разобранный тип.
o['дублей_цитат'] = cx.execute("""
    select count(*) from (
      select inn, quote from fact where coalesce(quote,'') <> ''
      group by inn, quote having count(*) > 1)""").fetchone()[0]
o['дублей_с_разным_tipom'] = cx.execute("""
    select count(*) from (
      select inn, quote from fact where coalesce(quote,'') <> ''
      group by inn, quote having count(distinct coalesce(equipment_type,'')) > 1)""").fetchone()[0]
o['строк_в_dublyah'] = cx.execute("""
    select coalesce(sum(n),0) from (
      select count(*) n from fact where coalesce(quote,'') <> ''
      group by inn, quote having count(*) > 1)""").fetchone()[0]
o['фактов_всего'] = cx.execute('select count(*) from fact').fetchone()[0]

# 3. Среда «не названа», хотя в цитате она есть словами.
o['sreda_ne_nazvana_a_v_citate_est'] = cx.execute("""
    select count(*) from fact
    where (coalesce(medium,'') = '' or lower(coalesce(medium,'')) like '%не назван%')
      and (lower(coalesce(quote,'')) like '%воздуш%' or lower(coalesce(quote,'')) like '%воздух%'
           or lower(coalesce(quote,'')) like '%воздуходувк%')""").fetchone()[0]

# 4. Компании без единого контакта — то, ради чего панель и открывают.
o['компаний_всего'] = cx.execute('select count(*) from company').fetchone()[0]
o['компаний_с_человеком'] = cx.execute(
    'select count(distinct inn) from person').fetchone()[0]
o['компаний_с_телефоном'] = cx.execute(
    "select count(distinct inn) from person where coalesce(phone,'') <> ''").fetchone()[0]

# 5. Короткие названия — ловушка, про которую предупреждала 1-я сессия («ВСК» в очереди).
# Имя колонки берём из схемы, а не из памяти: в company поля `name` нет.
kol = [r[1] for r in cx.execute('pragma table_info(company)')]
o['колонки_company'] = kol
imya = next((k for k in ('title', 'company', 'nazvanie', 'short_name', 'full_name') if k in kol),
            None)
if imya:
    o['компаний_с_коротким_именем'] = cx.execute(
        f'select count(*) from company where length(trim(coalesce("{imya}",\'\'))) <= 5'
    ).fetchone()[0]
    o['примеры_коротких'] = cx.execute(
        f'select coalesce("{imya}",\'\'), inn from company '
        f'where length(trim(coalesce("{imya}",\'\'))) <= 5 limit 8').fetchall()
print(json.dumps(o, ensure_ascii=False, indent=1))
