# -*- coding: utf-8 -*-
"""Пересмотр скрытий по СИЛЕ доказательства, а не по наличию слова.

ПОЧЕМУ ПРЕДЫДУЩЕЕ ПРАВИЛО НЕГОДНОЕ, и это моя ошибка, а не находка. Я считал доказательством
любой факт того же ИНН, где есть слово «центробежн», «нагнетатель», «турбокомпрессор» — или
где поле `equipment_type` панели говорит «центробежная». По этому правилу «к пересмотру»
попали 830 из 882 скрытых предприятий, и первые же цитаты показывают, что это мусор:

    «Поставка высотореза, воздуходувки и генератора бензинового»   — садовый листодув
    «Воздуходувка МОБИЛ К XBA90 ПРЕМИУМ 60В»                       — ручной листодув
    «Турбокомпрессор IVECO TRAKKER»                                — турбина грузовика
    «Поставка оборудования (экран, воздуходувка, гарнитура)»       — парковый инвентарь

У всех четырёх `equipment_type` = «центробежная», то есть я доказывал центробежность ТОЙ
САМОЙ разметкой, которую суд моделей и отверг. Круговое рассуждение: скрытие проверялось
уликой, из-за которой оно и появилось.

ЧТО СЧИТАТЬ ДОКАЗАТЕЛЬСТВОМ ЗДЕСЬ. Признаки промышленной машины, которых у листодува быть
не может, и каждый проверяется по ТЕКСТУ, а не по разметке:
  * заключение ЭПБ на техническое устройство с регистрационным номером ОПО (А##-#####-####);
  * марка из проверенного семейства (К-250-61-5, ЦК-135/8, ТВ-80-1,6 и подобные);
  * компрессорная установка/станция с мощностью или производительностью в м³/мин;
  * газоперекачивающий агрегат, нагнетатель в составе ГПА.
И отдельно — признаки бытового, при которых предприятие остаётся скрытым, даже если что-то
из верхнего списка нашлось: садовый, ручной, аккумуляторный, листодув, бензиновый триммер,
турбокомпрессор конкретной марки грузовика.
"""
import json
import re
import sqlite3

MARKA = re.compile(r'\b(?:К|ЦК|ТВ|НЦ|ТГ|КТК|Н)-\d{2,3}[\-/,\d]*\b')
OPO = re.compile(r'[А-ЯЁ]\d{2}-\d{4,6}(?:-\d{3,5})?')
PROM = re.compile(r'техническ\w+ устройств|компрессорн\w+ (?:установк|станци|цех)|'
                  r'газоперекачивающ|\bГПА\b|нагнетател\w* в составе|м³/мин|м3/мин|'
                  r'турбовоздуходувк|турбокомпрессор\w* (?:К|ЦК|ТК)-', re.I)
BYT = re.compile(r'садов|листодув|ручн\w+|аккумулятор|бензинов|воздуходув\w* (?:МОБИЛ|STIHL|'
                 r'ECHO|HUSQVARNA|MAKITA|BOSCH|CHAMPION)|высоторез|триммер|газонокосил|'
                 r'кусторез|гарнитур|IVECO|КАМАЗ|MAN\b|SCANIA|ЯМЗ|ТКР', re.I)

sale = sqlite3.connect(r'C:\seostat\data\centro_sales.db')
sale.execute('attach database ? as f', (r'C:\seostat\data\centrifugal.db',))
skr = sale.execute("""
    select inn, coalesce(value,''), coalesce(reason,''), coalesce(created_at,'')
    from hidden_item where kind='company'""").fetchall()

silno, slabo, netu = [], 0, 0
for inn, value, reason, kogda in skr:
    fakty = sale.execute("""
        select coalesce(c.source,''), coalesce(c.quote,''), coalesce(c.source_url,'')
        from f.fact c where c.inn = ? limit 60""", (inn,)).fetchall()
    ulики = []
    for src, quote, url in fakty:
        if BYT.search(quote):
            continue
        prichiny = []
        if OPO.search(quote) and PROM.search(quote):
            prichiny.append('заключение ЭПБ на техустройство ОПО')
        if MARKA.search(quote):
            prichiny.append('марка машины: ' + MARKA.search(quote).group(0))
        if PROM.search(quote):
            prichiny.append('признак промышленной машины')
        if prichiny and re.search(r'центробежн|нагнетател|турбокомпрессор|воздуходувк', quote, re.I):
            ulики.append({'istochnik': src, 'pochemu': '; '.join(sorted(set(prichiny))),
                          'citata': quote[:170]})
    if not fakty:
        netu += 1
        continue
    if not ulики:
        slabo += 1
        continue
    silno.append({'inn': inn, 'prichina_skrytiya': reason[:120], 'kogda': kogda,
                  'ulik': len(ulики), 'istochnikov': len({u['istochnik'] for u in ulики}),
                  'istochniki': ' | '.join(sorted({u['istochnik'] for u in ulики}))[:110],
                  'pochemu': ulики[0]['pochemu'], 'citata': ulики[0]['citata']})
silno.sort(key=lambda x: (-x['istochnikov'], -x['ulik']))
for z in silno:
    print('REC ' + json.dumps(z, ensure_ascii=False))
print('ИТОГ ' + json.dumps({'skrytiy_company': len(skr), 'silnyh_ulik': len(silno),
                            'slabo_skrytie_v_sile': slabo, 'faktov_net': netu},
                           ensure_ascii=False))
