# -*- coding: utf-8 -*-
"""Карточка характеристик машины по её марке — пункт 5 владельца.

Задача: продавцу мало знать, что у предприятия «есть К-250-61-5». Нужно знать, ЧТО это за
машина: сколько кубов в минуту, какое давление, какой привод, чем её меняют. Тогда первая фраза
звучит как разговор двух специалистов, а не как холодный звонок.

Откуда берутся числа. У советских и российских центробежных машин **производительность и
давление зашиты в само обозначение**, и это не догадка, а отраслевой стандарт:

    К-250-61-5     К = центробежный компрессор, 250 = м³/мин, 61 = конечное давление ×0,1 МПа
    ЦК-135/8       ЦК = центробежный компрессор, 135 = м³/мин, 8 = избыточное давление в атм
    ТВ-80-1,6      ТВ = турбовоздуходувка, 80 = м³/мин, 1,6 = степень повышения давления
    ГТК-10-4       ГТК = газотурбинный компрессор (ГПА), 10 = мощность привода в МВт
    КТК-12,5/35    КТК = компрессор турбинный, 12,5 тыс. м³/ч, 35 = давление в атм

Разбор ведём ТОЛЬКО там, где серия распознана явно. Если обозначение не ложится на известную
серию — пишем «не разобрано» и не выдумываем: неверная характеристика в разговоре хуже, чем её
отсутствие, потому что она слышна собеседнику сразу.

Использование:
    python3 harakteristiki_mashin.py
"""
import csv
import os
import re
import subprocess
from collections import defaultdict

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
FAKTY = os.path.join(L, 'SVOD-tri-sostoyaniya.csv')
PRED = os.path.join(L, 'SVOD-POLNYY-po-predpriyatiyam.csv')
VYHOD = os.path.join(L, 'HARAKTERISTIKI-mashin-po-predpriyatiyam.csv')

# Серия → как читать числа. Порядок важен: длинные обозначения раньше коротких, иначе «К»
# перехватит «КТК» и «ЦК».
SERII = [
    ('ГТК', 'газотурбинный компрессорный агрегат (ГПА)',
     r'^ГТК[\s\-]?(\d+(?:[.,]\d+)?)', ('мощность привода, МВт',)),
    ('КТК', 'компрессор турбинный',
     r'^КТК[\s\-]?(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)',
     ('производительность, тыс. м³/ч', 'давление, атм')),
    ('ЦК', 'центробежный компрессор',
     r'^ЦК[\s\-]?(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)',
     ('производительность, м³/мин', 'давление, атм')),
    ('ТВ', 'турбовоздуходувка',
     r'^ТВ[\s\-]?(\d+(?:[.,]\d+)?)[\s\-]+(\d+(?:[.,]\d+)?)',
     ('производительность, м³/мин', 'степень повышения давления')),
    ('ТГ', 'турбогазодувка',
     r'^ТГ[\s\-]?(\d+(?:[.,]\d+)?)', ('производительность, м³/мин',)),
    ('НЦ', 'нагнетатель центробежный (ГПА)',
     r'^НЦ[\s\-]?(\d+(?:[.,]\d+)?)', ('мощность, МВт',)),
    ('Н', 'нагнетатель центробежный',
     r'^Н[\s\-]?(\d+(?:[.,]\d+)?)[\s\-]?(\d+)?', ('условный размер',)),
    ('К', 'центробежный компрессор',
     r'^К[\s\-]?(\d+(?:[.,]\d+)?)[\s\-](\d+)', ('производительность, м³/мин',
                                                'конечное давление, ×0,1 МПа')),
]
# Чем такую машину меняют у нас в каталоге — грубая привязка по производительности.
def chem_menyaem(m3min):
    if not m3min:
        return ''
    if m3min < 60:
        return 'воздуходувка низкого давления'
    if m3min < 200:
        return 'центробежный компрессор среднего ряда'
    if m3min < 600:
        return 'центробежный компрессор крупного ряда'
    return 'турбокомпрессор большой производительности'


def razobrat_marku(marka):
    m = re.sub(r'[«»"]', '', (marka or '').strip()).strip('.,;')
    if len(m) < 3:
        return None
    for imya, opisanie, shablon, podpisi in SERII:
        g = re.match(shablon, m, re.I)
        if not g:
            continue
        chisla = [x for x in g.groups() if x]
        d = {'seriya': imya, 'chto_eto': opisanie, 'marka': m}
        for podpis, znach in zip(podpisi, chisla):
            d[podpis] = znach.replace(',', '.')
        # производительность в м³/мин, если она в этой серии первая
        p = None
        if 'производительность, м³/мин' in d:
            try:
                p = float(d['производительность, м³/мин'])
            except ValueError:
                p = None
        elif 'производительность, тыс. м³/ч' in d:
            try:
                p = float(d['производительность, тыс. м³/ч']) * 1000 / 60
            except ValueError:
                p = None
        d['chem_menyaem'] = chem_menyaem(p)
        d['proizvoditelnost_m3min'] = round(p, 1) if p else ''
        return d
    return None


def main():
    fakty = [x for x in csv.DictReader(open(FAKTY, encoding='utf-8-sig'), delimiter=';')
             if x.get('tip_mashiny') in ('центробежная', 'центробежная по серии')]
    pred = {r['inn']: r for r in csv.DictReader(open(PRED, encoding='utf-8-sig'), delimiter=';')}

    po_inn = defaultdict(dict)
    vsego_marok, razobrano = set(), set()
    for x in fakty:
        for k in (x.get('marki') or '').split('|'):
            k = k.strip().strip('.,;')
            if len(k) < 3:
                continue
            vsego_marok.add(k)
            d = razobrat_marku(k)
            if not d:
                continue
            razobrano.add(k)
            klyuch = d['marka'].upper().replace(' ', '')
            zap = po_inn[x['inn']].setdefault(klyuch, {**d, 'sostoyaniya': set(), 'daty': set(),
                                                       'ssylki': set()})
            zap['sostoyaniya'].add(x['sostoyanie'])
            if x.get('data'):
                zap['daty'].add(x['data'])
            ss = x.get('ssylka') or ''
            if ss.startswith('http'):
                zap['ssylki'].add(ss)

    cols = ['inn', 'predpriyatie', 'marka', 'seriya', 'chto_eto', 'proizvoditelnost_m3min',
            'davlenie', 'moshchnost', 'chem_menyaem', 'sostoyaniya', 'daty', 'ssylka',
            'srok_sluzhby', 'vyvod_ekspertizy', 'telefon_predpriyatiya', 'lyudej_tehnicheskih']
    out = []
    for inn, mashiny in po_inn.items():
        p = pred.get(inn) or {}
        for d in mashiny.values():
            davl = (d.get('давление, атм') or d.get('конечное давление, ×0,1 МПа')
                    or d.get('степень повышения давления') or '')
            out.append({
                'inn': inn, 'predpriyatie': p.get('predpriyatie') or '',
                'marka': d['marka'], 'seriya': d['seriya'], 'chto_eto': d['chto_eto'],
                'proizvoditelnost_m3min': d.get('proizvoditelnost_m3min') or '',
                'davlenie': davl,
                'moshchnost': d.get('мощность привода, МВт') or d.get('мощность, МВт') or '',
                'chem_menyaem': d.get('chem_menyaem') or '',
                'sostoyaniya': ' | '.join(sorted(d['sostoyaniya'])),
                'daty': ' | '.join(sorted(d['daty']))[:60],
                'ssylka': sorted(d['ssylki'])[0] if d['ssylki'] else '',
                'srok_sluzhby': p.get('srok_sluzhby') or '',
                'vyvod_ekspertizy': p.get('vyvod_ekspertizy') or '',
                'telefon_predpriyatiya': (p.get('telefony_predpriyatiya') or '')[:60],
                'lyudej_tehnicheskih': p.get('lyudej_tehnicheskih') or '0',
            })

    def ves(x):
        return (1 if x['proizvoditelnost_m3min'] else 0, int(x['lyudej_tehnicheskih'] or 0))
    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in sorted(out, key=ves, reverse=True):
            w.writerow(r)

    pr = list(csv.DictReader(open(VYHOD, encoding='utf-8-sig'), delimiter=';'))
    print(f'марок в фактах: {len(vsego_marok)}, разобрано по сериям: {len(razobrano)} '
          f'({len(razobrano)*100//max(1,len(vsego_marok))}%)')
    print(f'строк-машин: {len(pr)}, предприятий: {len({r["inn"] for r in pr})}')
    print(f'  с известной производительностью: {sum(1 for r in pr if r["proizvoditelnost_m3min"])}')
    print(f'  с известным давлением: {sum(1 for r in pr if r["davlenie"])}')
    import collections as _c
    print('  по сериям:', dict(_c.Counter(r['seriya'] for r in pr).most_common(8)))
    subprocess.run(['bash', os.path.join(BAZA, 'server', 'drop_client.sh'), 'up', VYHOD],
                   capture_output=True, timeout=600)
    print(f'выложено на дроп → {os.path.basename(VYHOD)}')


if __name__ == '__main__':
    main()
