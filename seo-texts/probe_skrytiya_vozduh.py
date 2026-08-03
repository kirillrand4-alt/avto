# -*- coding: utf-8 -*-
"""Итог пересмотра: скрытые предприятия с промышленной ВОЗДУШНОЙ машиной — то есть наши.

ПУТЬ К ЭТОМУ ЧИСЛУ, ЧЕСТНО. Сначала правило было «есть соседний факт со словом центробежный»
— оно дало 830 предприятий из 882 и оказалось круговым: доказывало разметкой панели, которую
суд моделей и отверг, вытаскивая садовые листодувы и турбины грузовиков. Правило по силе
улики (регистрационный номер ОПО, марка проверенного семейства, мощность и производительность,
при отсечении бытового) оставило 74. Но владельцу нужны ВОЗДУШНЫЕ, а среди этих 74 много
газовых — нагнетатели ГПА, ДКС, НЦ-16 на природном газе, и они скрыты правильно.

Здесь остаётся последний срез: промышленная машина И воздух. Печатается он целиком, потому
что маленький; по газовым и неопределённым — только числа.
"""
import json
import re
import sqlite3

MARKA = re.compile(r'\b(?:К|ЦК|ТВ|НЦ|ТГ|КТК|Н)-\d{2,3}[\-/,\d]*\b')
OPO = re.compile(r'[А-ЯЁ]\d{2}-\d{4,6}(?:-\d{3,5})?')
PROM = re.compile(r'техническ\w+ устройств|компрессорн\w+ (?:установк|станци|цех)|'
                  r'газоперекачивающ|\bГПА\b|нагнетател\w* в составе|м³/мин|м3/мин|'
                  r'турбовоздуходувк|\bкВт\b', re.I)
BYT = re.compile(r'садов|листодув|ручн\w+|аккумулятор|бензинов|высоторез|триммер|газонокосил|'
                 r'кусторез|гарнитур|IVECO|КАМАЗ|MAN\b|SCANIA|ЯМЗ|ТКР|МОБИЛ|STIHL|ECHO|'
                 r'HUSQVARNA|MAKITA|BOSCH|CHAMPION', re.I)
GAZ = re.compile(r'природн\w*\s*газ|\bГПА\b|газоперекачив|\bДКС\b|попутн\w*\s*газ|синтез-газ|'
                 r'азот|кислород|аммиак|водород|этилен|пропилен|сероводород', re.I)
VOZDUH = re.compile(r'воздух|воздушн|воздуходувк|турбовоздуходувк|пневмо|дутьев', re.I)

sale = sqlite3.connect(r'C:\seostat\data\centro_sales.db')
sale.execute('attach database ? as f', (r'C:\seostat\data\centrifugal.db',))
skr = sale.execute("select inn, coalesce(reason,''), coalesce(created_at,'') "
                   "from hidden_item where kind='company'").fetchall()

vozduh, gaz, ne_nazvana, bez_ulik = [], 0, 0, 0
for inn, reason, kogda in skr:
    fakty = sale.execute("select coalesce(c.source,''), coalesce(c.quote,'') "
                         "from f.fact c where c.inn = ? limit 60", (inn,)).fetchall()
    uliki = []
    for src, q in fakty:
        if BYT.search(q) or not re.search(r'центробежн|нагнетател|турбокомпрессор|воздуходувк',
                                          q, re.I):
            continue
        if OPO.search(q) or MARKA.search(q) or PROM.search(q):
            uliki.append((src, q))
    if not uliki:
        bez_ulik += 1
        continue
    v = [u for u in uliki if VOZDUH.search(u[1]) and not GAZ.search(u[1])]
    g = [u for u in uliki if GAZ.search(u[1])]
    if v:
        # Личные номера ради этого и нужны: сразу тянем, есть ли у предприятия человек.
        lyudi = sale.execute(
            "select count(*), sum(case when coalesce(phone,'')<>'' then 1 else 0 end) "
            "from f.person where inn = ?", (inn,)).fetchone()
        vozduh.append({'inn': inn, 'ulik_vozduh': len(v), 'vsego_ulik': len(uliki),
                       'istochnik': v[0][0], 'citata': v[0][1][:150],
                       'lyudey': lyudi[0] or 0, 's_telefonom': lyudi[1] or 0,
                       'prichina_skrytiya': reason[:100], 'kogda': kogda})
    elif g:
        gaz += 1
    else:
        ne_nazvana += 1
vozduh.sort(key=lambda x: (-x['s_telefonom'], -x['ulik_vozduh']))
# ВЫДАЧА СТРАНИЦАМИ. Раннер возвращает хвост вывода, а не весь вывод: на 43 записях начало
# срезалось молча. Страница задаётся аргументом, и её номер печатается рядом с итогом —
# так видно, что забрано, а что ещё нет.
import sys
STR = int(sys.argv[1]) if len(sys.argv) > 1 else 0
RAZM = 15
for z in vozduh[STR * RAZM:(STR + 1) * RAZM]:
    z['citata'] = z['citata'][:100]
    z['prichina_skrytiya'] = z['prichina_skrytiya'][:60]
    print('REC ' + json.dumps(z, ensure_ascii=False))
print('ИТОГ ' + json.dumps({'stranica': STR, 'na_stranice': RAZM,
                            'skrytiy_company': len(skr), 'VOZDUSHNYE_k_vozvratu': len(vozduh),
                            'gazovye_skrytie_verno': gaz, 'sreda_ne_nazvana': ne_nazvana,
                            'bez_promyshlennyh_ulik': bez_ulik}, ensure_ascii=False))
