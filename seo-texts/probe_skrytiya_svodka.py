# -*- coding: utf-8 -*-
"""Проверка собственной находки: 19 077 скрытий «к пересмотру» — это слишком похоже на ошибку.

ПОВОД НЕ ДОВЕРЯТЬ СЕБЕ. Прогон сказал: из 19 358 скрытий с причиной «центробежность не
доказана» у 19 077 есть соседний факт, доказывающий центробежность. Доля 98,5 % — это либо
настоящий системный провал разметки, либо мой запрос доказывает не то, что я думаю. Разница
принципиальна, а проверяется дёшево:

1. ВИД СКРЫТИЯ. Если прячется контакт или значение, а не предприятие, «центробежность
   предприятия» вообще не была основанием — и совпадение причины ничего не значит.
2. ТА ЖЕ ЛИ ЭТО КАРТОЧКА. Если «доказательство» — та самая запись, которую и скрыли, я
   доказываю центробежность самой отвергнутой карточкой. Сверяю источник и ссылку.
3. СКОЛЬКО РАЗНЫХ ПРЕДПРИЯТИЙ. 19 077 строк могут оказаться сотней ИНН, размноженной по
   числу контактов: в выдаче уже видно 9718133155 семь раз подряд.
4. ЧТО В ПРИЧИНЕ ДОСЛОВНО. Массовая операция могла проставить один шаблон всем подряд.

Печатаю только сводные числа — они в хвост вывода помещаются целиком.
"""
import json
import sqlite3

sale = sqlite3.connect(r'C:\seostat\data\centro_sales.db')
sale.execute('attach database ? as f', (r'C:\seostat\data\centrifugal.db',))
USL = ("lower(coalesce(reason,'')) like '%центробежн%' and ("
       "lower(coalesce(reason,'')) like '%не доказан%' or "
       "lower(coalesce(reason,'')) like '%не подтвержд%' or "
       "lower(coalesce(reason,'')) like '%нет доказ%')")
o = {}
o['скрытий_всего_в_базе'] = sale.execute('select count(*) from hidden_item').fetchone()[0]
o['по_нашей_причине'] = sale.execute(f'select count(*) from hidden_item where {USL}').fetchone()[0]
o['разных_ИНН_по_причине'] = sale.execute(
    f'select count(distinct inn) from hidden_item where {USL}').fetchone()[0]
o['по_виду'] = dict(sale.execute(
    f'select kind, count(*) from hidden_item where {USL} group by kind order by 2 desc').fetchall())
o['разных_ИНН_по_виду'] = dict(sale.execute(
    f'select kind, count(distinct inn) from hidden_item where {USL} group by kind').fetchall())
o['причины_дословно'] = sale.execute(
    f'select reason, count(*) from hidden_item where {USL} group by reason order by 2 desc limit 8'
).fetchall()
o['кто_скрыл'] = dict(sale.execute(
    f"select coalesce(nullif(trim(username),''),'(без подписи)'), count(*) "
    f'from hidden_item where {USL} group by 1').fetchall())
o['когда'] = sale.execute(
    f"select substr(coalesce(created_at,''),1,10), count(*) from hidden_item where {USL} "
    f'group by 1 order by 1').fetchall()[:10]

# Сколько ИНН имеют доказательство, и отличается ли источник доказательства от скрытого значения.
inny = [r[0] for r in sale.execute(f'select distinct inn from hidden_item where {USL}')]
s_dok = 0
sovpalo = 0
for inn in inny:
    dok = sale.execute("""
        select coalesce(c.source,''), coalesce(c.source_url,'')
        from f.fact c where c.inn = ?
          and (lower(coalesce(c.equipment_type,'')) like '%центробежн%'
               or lower(coalesce(c.quote,'')) like '%центробежн%'
               or lower(coalesce(c.quote,'')) like '%турбокомпрессор%'
               or lower(coalesce(c.quote,'')) like '%нагнетател%') limit 8""", (inn,)).fetchall()
    if not dok:
        continue
    s_dok += 1
    # Скрытые значения этого ИНН: если ссылка доказательства среди них, доказываю скрытым.
    skryto = {r[0] for r in sale.execute(
        f'select coalesce(value,\'\') from hidden_item where inn=? and {USL}', (inn,))}
    if any(u and u in skryto for _, u in dok):
        sovpalo += 1
o['ИНН_с_доказательством'] = s_dok
o['ИНН_где_доказательство_и_есть_скрытое'] = sovpalo
print(json.dumps(o, ensure_ascii=False, indent=1))
