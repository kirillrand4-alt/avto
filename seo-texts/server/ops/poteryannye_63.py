# -*- coding: utf-8 -*-
"""За что сборщик выбросил факты у 63 предприятий, которые нашла 3-я сессия.

Третья сессия замерила: 1 204 карточки помечены «центробежная», и у 171 из них
НЕТ ни одного центробежного факта. Она разделила причины — 108 не подтверждены
никем (скрыла), а 63 имеют факт в разметке 2-й сессии, который не доехал до
панели. Сборщик отбросил 12 912 фактов, и часть, похоже, зря.

Скрытием это не лечится, чинить надо правило отбора — а правило чинят по
замеру, а не по трём примерам. Здесь замер: берём факты этих предприятий из
базы панели, прогоняем через боевой `centro_medium.rejection_reason` и
смотрим, за что каждый выброшен и много ли среди выброшенных таких, где в
тексте прямо названа НАША машина.

Файл 3-й сессии — 121 строка на 63 предприятия, и часть из них отсеяна
СПРАВЕДЛИВО: «ЦЕНТРОБЕЖНЫЙ НАСОС ПОЗ. Н-310» это насос, ему в базе
компрессоров делать нечего. Поэтому оп ничего не чинит сам, он только
показывает разбивку — решение по правилу принимается после неё.

Запуск: python poteryannye_63.py
"""
import csv
import io
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r'C:\seostat')
from app.services import centro_medium as CM  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'
БАЗА = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ФАЙЛ = 'POTERYANO-PRI-SBORKE-63-ot-3-sessii.csv'
# «наша машина названа прямо» — те же признаки, что у боевого правила, плюс
# воздуходувка: её правило сегодня спасением не считает, и это как раз то,
# что надо проверить числом.
_НАША = re.compile(
    r'(?:турбовоздуходувк\w*|воздуходувк\w*|центробежн\w*\s+компрессор\w*|'
    r'\bцк[\s-]?\d|\bк-?\d{3}[-\s]?\d{2}|\b\d{2}вц[\s-]?\d|'
    r'турбокомпрессор\w*|нагнетател\w*)', re.I)


def читать():
    п = os.path.join(ДРОП, ФАЙЛ)
    if not os.path.exists(п):
        raise SystemExit(f'нет файла {ФАЙЛ} на дропе')
    csv.field_size_limit(10 ** 7)
    сыр = open(п, encoding='utf-8-sig', errors='replace').read()
    ряды = list(csv.DictReader(io.StringIO(сыр), delimiter=';'))
    if ряды and len(ряды[0]) <= 1:
        ряды = list(csv.DictReader(io.StringIO(сыр), delimiter=','))
    return ряды


def main():
    ряды = читать()
    инны = {re.sub(r'\D', '', r.get('inn') or '')[:12] for r in ряды}
    инны.discard('')
    ярлыки = Counter((r.get('tip_u_2_sessii') or '').strip() for r in ряды)

    cx = sqlite3.connect(f'file:{БАЗА}?mode=ro', uri=True, timeout=15)
    кол = [c[1] for c in cx.execute('PRAGMA table_info("fact")')]
    сп = ','.join('?' * len(инны))
    строки = cx.execute(
        f'SELECT * FROM fact WHERE inn IN ({сп})', tuple(инны)).fetchall()
    cx.close()

    причины = Counter()
    спасаемые = Counter()
    примеры = defaultdict(list)
    по_предпр = defaultdict(lambda: {'всего': 0, 'чистых': 0, 'спасаемых': 0})
    for с in строки:
        row = dict(zip(кол, с))
        факт = {
            'status': row.get('status') or row.get('chto') or '',
            'model': row.get('model') or row.get('kto_ili_marka') or '',
            'equipment_type': (row.get('equipment_type')
                               or row.get('dolzhnost_ili_tip') or ''),
            'medium': row.get('medium') or row.get('rol') or '',
            'evidence': row.get('evidence') or row.get('chem_dokazano') or '',
            'quote': row.get('quote') or row.get('citata') or '',
        }
        и = str(row.get('inn') or '')
        по_предпр[и]['всего'] += 1
        причина = CM.rejection_reason(факт)
        причины[причина or 'ОСТАВЛЕН'] += 1
        if not причина:
            по_предпр[и]['чистых'] += 1
            continue
        текст = ' | '.join(str(v) for v in факт.values())
        if _НАША.search(текст):
            спасаемые[причина] += 1
            по_предпр[и]['спасаемых'] += 1
            if len(примеры[причина]) < 3:
                примеры[причина].append({
                    'inn': и, 'марка': факт['model'][:40],
                    'текст': (факт['evidence'] or факт['quote'])[:110]})

    без_чистых = [и for и, v in по_предпр.items() if not v['чистых']]
    спасёт = [и for и in без_чистых if по_предпр[и]['спасаемых']]

    # ГЛАВНАЯ ПРОВЕРКА, которую первый прогон не сделал. «Факт не доехал до
    # панели» проверяется не тем, отбрасывает ли его фильтр, а тем, ЛЕЖИТ ЛИ
    # ОН В БАЗЕ. Фильтр может быть ни при чём: строка могла не попасть в
    # исходный CSV сборки. Сверяем по ссылке-первоисточнику — она уникальна
    # для строки и переживает любую переформулировку текста.
    ссылки_в_базе = defaultdict(set)
    for с in строки:
        row = dict(zip(кол, с))
        у = (row.get('source_url') or '').strip()
        if у:
            ссылки_в_базе[str(row.get('inn') or '')].add(у)
    доехало = не_доехало = без_ссылки = 0
    примеры_недоехавших = []
    for r in ряды:
        и = re.sub(r'\D', '', r.get('inn') or '')[:12]
        у = (r.get('ssylka') or '').strip()
        if not у:
            без_ссылки += 1
            continue
        if у in ссылки_в_базе.get(и, ()):
            доехало += 1
        else:
            не_доехало += 1
            if len(примеры_недоехавших) < 4:
                примеры_недоехавших.append(
                    {'inn': и, 'тип_у_2й': (r.get('tip_u_2_sessii') or '')[:40],
                     'ссылка': у[:90]})

    # и доказывают ли вообще факты этих предприятий ЦЕНТРОБЕЖНОСТЬ
    центробежных = 0
    предпр_с_центробежным = set()
    for с in строки:
        row = dict(zip(кол, с))
        т = ' | '.join(str(row.get(k) or '') for k in
                       ('status', 'model', 'equipment_type', 'evidence', 'quote'))
        if re.search(r'центробежн|турбокомпресс|турбовоздуходувк', т, re.I):
            центробежных += 1
            предпр_с_центробежным.add(str(row.get('inn') or ''))

    print(json.dumps({
        'предприятий_в_файле': len(инны),
        'ярлыки_2й_сессии': ярлыки.most_common(8),
        'фактов_у_них_в_базе': len(строки),
        'причины_отсева': причины.most_common(),
        'из_отсеянных_НАША_машина_названа_прямо': спасаемые.most_common(),
        'предприятий_без_единого_чистого_факта': len(без_чистых),
        'из_них_спаслись_бы_смягчением': len(спасёт),
        'строк_файла_НАШЛОСЬ_в_базе_по_ссылке': доехало,
        'строк_файла_НЕ_нашлось': не_доехало,
        'строк_файла_без_ссылки': без_ссылки,
        'фактов_со_словом_центробежн': центробежных,
        'предприятий_с_таким_фактом': len(предпр_с_центробежным),
        'примеры_недоехавших': примеры_недоехавших,
    }, ensure_ascii=False, indent=1))
    for причина, сп2 in примеры.items():
        print(f'\n--- {причина} ---')
        for э in сп2:
            print(f'  {э["inn"]} [{э["марка"]}] {э["текст"]}')


if __name__ == '__main__':
    main()
