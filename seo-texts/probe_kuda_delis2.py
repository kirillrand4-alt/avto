# -*- coding: utf-8 -*-
"""Кто и чем скрыл 326 предприятий в 19:00 — самая крупная партия из всех.

ПОЧЕМУ ИМЕННО ОНА ТРЕВОЖИТ. Причина записана как «марки в фактах не совпали со словарём
воздушных центробежных — выкидываю». Я сегодня этот самый словарь строила и САМА ЖЕ его
откатила, измерив: из 307 марок с вердиктом поле `model` панели подтверждает 102, известные
семейства — 39, а девять вердиктов пришли вообще не от компрессоров (Л-35/11-300 — риформинг,
УКПГ-4 — подготовка газа); ПК-1/2/3 с 257 упоминаниями оказались позиционными обозначениями.
Словарь, у которого надёжны 39 марок из 2 915, годится чтобы ДОБАВИТЬ среду там, где её нет.
Скрывать им предприятия — значит выкидывать по признаку, которого у машины просто не записали.

Печатаю: полные причины, подписи, время, и — главное — сколько среди скрытых этой партией
таких, у кого центробежность доказана ТЕКСТОМ, а не маркой.
"""
import json
import re
import sqlite3

cx = sqlite3.connect(r'C:\seostat\data\centro_sales.db')
cx.execute('attach database ? as f', (r'C:\seostat\data\centrifugal.db',))
o = {}
o['компаний_в_базе'] = cx.execute('select count(*) from f.company').fetchone()[0]
o['скрытых_ИНН'] = cx.execute(
    "select count(distinct inn) from hidden_item where kind='company'").fetchone()[0]
o['видно_сейчас'] = o['компаний_в_базе'] - o['скрытых_ИНН']
o['по_часам'] = cx.execute(
    "select substr(coalesce(created_at,''),1,13), count(*) from hidden_item "
    "where kind='company' group by 1 order by 1").fetchall()

PARTIYA = "kind='company' and coalesce(reason,'') like 'марки в фактах не совпали%'"
o['партия_19h'] = cx.execute(f'select count(*) from hidden_item where {PARTIYA}').fetchone()[0]
o['партия_причина_полностью'] = cx.execute(
    f'select distinct coalesce(reason,\'\') from hidden_item where {PARTIYA} limit 3').fetchall()
o['партия_подписи'] = dict(cx.execute(
    f"select coalesce(nullif(trim(username),''),'(без подписи)'), count(*) "
    f'from hidden_item where {PARTIYA} group by 1').fetchall())

# Сколько из них имеют факт, где центробежность доказана ТЕКСТОМ (не маркой).
inny = [r[0] for r in cx.execute(f'select distinct inn from hidden_item where {PARTIYA}')]
tekstom, vozdushnyh, primery = 0, 0, []
for inn in inny:
    f = cx.execute("""
        select coalesce(quote,''), coalesce(source,'') from f.fact
        where inn = ? and (lower(coalesce(quote,'')) like '%центробежн%'
                           or lower(coalesce(quote,'')) like '%турбокомпрессор%'
                           or lower(coalesce(quote,'')) like '%турбовоздуходувк%'
                           or lower(coalesce(quote,'')) like '%нагнетател%') limit 6""",
                   (inn,)).fetchall()
    if not f:
        continue
    tekstom += 1
    v = [x for x in f if re.search(r'воздух|воздушн|воздуходувк|пневмо|дутьев', x[0], re.I)
         and not re.search(r'природн\w*\s*газ|\bГПА\b|газоперекач', x[0], re.I)]
    if v:
        vozdushnyh += 1
        if len(primery) < 6:
            primery.append({'inn': inn, 'istochnik': v[0][1], 'citata': v[0][0][:150]})
o['из_партии_центробежность_доказана_текстом'] = tekstom
o['из_них_ВОЗДУШНЫХ_по_тексту'] = vozdushnyh
o['примеры'] = primery
print(json.dumps(o, ensure_ascii=False, indent=1))
