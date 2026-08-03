# -*- coding: utf-8 -*-
"""Сузить находку до того, что действительно вредит: скрытия ПРЕДПРИЯТИЙ, а не отдельных фактов.

ЧТО ВЫЯСНИЛОСЬ ПРИ ПРОВЕРКЕ. Тревога «19 077 скрытий к пересмотру» была раздутой, и вот чем:
из 19 358 скрытий с этой причиной 19 248 имеют вид `fact` — они прячут ОДНУ карточку, у
которой центробежность действительно не доказана ни разметкой, ни текстом. Предприятие при
этом остаётся видимым через остальные свои карточки, и «соседний факт доказывает» для них не
ошибка, а норма: так и задумано. Считать их к пересмотру значило считать правильную работу
поломкой.

Вредят другие — 110 скрытий вида `company`: они прячут предприятие целиком. Их и проверяем.
Оба ИНН из вопроса владельца (1003018230 и 7017156263) должны быть здесь.

Отдельно печатается, ЧЕМ доказана центробежность, чтобы решение принималось по цитате, а не
по слову «доказано»: источник, тип оборудования из разметки и кусок текста карточки.
"""
import json
import sqlite3

sale = sqlite3.connect(r'C:\seostat\data\centro_sales.db')
sale.execute('attach database ? as f', (r'C:\seostat\data\centrifugal.db',))
skr = sale.execute("""
    select inn, coalesce(value,''), coalesce(reason,''), coalesce(username,''),
           coalesce(created_at,'')
    from hidden_item where kind='company'
""").fetchall()
k_peresmotru, v_sile = [], 0
for inn, value, reason, user, kogda in skr:
    dok = sale.execute("""
        select coalesce(c.source,''), coalesce(c.equipment_type,''),
               substr(coalesce(c.quote,''),1,150), coalesce(c.source_url,'')
        from f.fact c where c.inn = ?
          and (lower(coalesce(c.equipment_type,'')) like '%центробежн%'
               or lower(coalesce(c.quote,'')) like '%центробежн%'
               or lower(coalesce(c.quote,'')) like '%турбокомпрессор%'
               or lower(coalesce(c.quote,'')) like '%турбовоздуходувк%'
               or lower(coalesce(c.quote,'')) like '%нагнетател%') limit 10""", (inn,)).fetchall()
    if not dok:
        v_sile += 1
        continue
    # Разметка и текст — независимые свидетельства; считаем их порознь.
    po_razmetke = sum(1 for d in dok if 'центробежн' in (d[1] or '').lower())
    k_peresmotru.append({'inn': inn, 'predpriyatie': value[:70], 'prichina': reason[:110],
                         'kto': user, 'kogda': kogda, 'faktov': len(dok),
                         'po_razmetke': po_razmetke,
                         'istochnikov': len({d[0] for d in dok if d[0]}),
                         'istochniki': ' | '.join(sorted({d[0] for d in dok if d[0]}))[:120],
                         'citata': dok[0][2]})
k_peresmotru.sort(key=lambda x: (-x['istochnikov'], -x['faktov']))
for z in k_peresmotru:
    print('REC ' + json.dumps(z, ensure_ascii=False))
print('ИТОГ ' + json.dumps({'skrytiy_company': len(skr), 'k_peresmotru': len(k_peresmotru),
                            'v_sile': v_sile}, ensure_ascii=False))
