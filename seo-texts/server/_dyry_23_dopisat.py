# -*- coding: utf-8 -*-
"""Дописать в общий файл находку про .рф-домены и разбор «почему пусто»."""
import json
import os

p = r'C:\sender\_tmp\diagnoz-dyry.json'
s = json.load(open(p, encoding='utf-8'))
s['dyra1_pasporta']['находка_рф_домены'] = {
    'что': 'у заблокированных пустым site в кэше почти всегда записан кириллический '
           'домен, а в companies.site/cand_site пусто',
    'доказанные_привязкой_328_из_них_не_ASCII': 313,
    'недоказанные_2760_из_них_не_ASCII': 1611,
    'в_companies_site_не_ASCII_всего': 1889,
    'cand_site_не_ASCII': 804, 'punycode_xn__': 1,
    'выборка_кэша_1500': {'с_не_ASCII_сайтом': 125, 'сайт_в_базе_есть': 66,
                          'сайт_в_базе_пуст': 59},
    'оценка_на_весь_кэш': {'не_ASCII_сайтов': 4513, 'из_них_без_сайта_в_базе': 2130},
    'вывод': 'кириллические домены теряются на записи в companies примерно в половине '
             'случаев (47%) против 11% потери сайта в среднем по кэшу'}
try:
    d = json.load(open(r'C:\sender\_tmp\dyra2_pochemu.json', encoding='utf-8'))
    s['dyra2_pustye_pasporta']['почему'] = {
        'verified_у_пустых': d['verified_pustye'],
        'verified_у_полных': d['verified_polnye'],
        'CSS_мусор_у_пустых': d['css_pustye'],
        'CSS_мусор_у_полных': d['css_polnye'],
        'вывод': 'мусор в тексте НЕ объясняет разницу (12% против 10%); '
                 'объясняет непроверенная привязка сайта: подтверждённых ИНН/провайдером '
                 '21% у пустых против 41% у полных'}
except Exception as e:  # noqa: BLE001
    s['dyra2_pustye_pasporta']['почему'] = {'ошибка': str(e)[:120]}
with open(p, 'w', encoding='utf-8') as f:
    json.dump(s, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
print('ЗАПИСАН', p, os.path.getsize(p), 'байт')
print('разделы:', json.dumps(list(s), ensure_ascii=False))
for k in ('dyra1_pasporta', 'dyra2_pustye_pasporta', 'dyra3_kontakty', 'dyra4_ne_obhodili'):
    print(' ', k, '->', json.dumps(list(s[k]), ensure_ascii=False))
