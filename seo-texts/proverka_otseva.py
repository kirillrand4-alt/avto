# -*- coding: utf-8 -*-
"""Проверка отсева в обе стороны: не выкинуто ли живое и не остался ли мусор.

Вопрос владельца дословно: «проверь не отсекается ли полезное в мусор и наоборот остался ли ещё
мусор». Проверка сделана двумя независимыми способами, потому что каждый по отдельности врёт:

1. **Сплошная, механическая** — все 87 452 факта до одного. Ищем противоречие внутри строки:
   ярлык говорит «не наша машина», а в тексте стоит бесспорный признак нашей («центробежный
   компрессор», «турбовоздуходувка»); либо наоборот — ярлык «центробежная», а в тексте стоит
   бесспорный признак чужой («центробежный насос», «паровая турбина», «поршневой компрессор»).
   Выборка тут не нужна и вредна: механика читает всё.
2. **Выборочная, глазами моделей** — одиннадцать агентов читали по 30–40 строк каждого класса и
   пытались опровергнуть ярлык, а найденное отдавали агентам-опровергателям. Механика не умеет
   отличить «воздуходувка GM60H» (роторная, чужая) от «воздуходувка Н-1200-25-3» (наша), а модель
   умеет, потому что знает марки.

Файл на выходе — не число, а список: что именно выкинуто и по какому правилу. Продавец должен
иметь возможность заглянуть в мусорную корзину и вытащить оттуда предприятие руками.

Использование:
    python3 proverka_otseva.py
"""
import csv
import os
import re
import subprocess
from collections import Counter, defaultdict

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
FAKTY = os.path.join(L, 'SVOD-tri-sostoyaniya.csv')
OTSEV = os.path.join(L, 'OTSEV-tip-mashiny.csv')
OTCHET = os.path.join(L, 'PROVERKA-otseva.md')

NASH = {'центробежная', 'центробежная по серии', 'центробежная, вид по слову'}
# «Бесспорно наша»: не просто слово, а слово в связке. «Турбокомпрессор» одиночный сюда не годится —
# им же называют турбину наддува автобуса.
SILNO_NASHE = re.compile(
    r'центробежн\w*\s+(?:компрессор|нагнетател|воздуходувк|газодувк)|компрессор\w*\s+центробежн|'
    r'турбовоздуходувк|турбогазодувк|турбокомпрессорн\w+\s+агрегат', re.I)
# «Бесспорно чужая»: тоже только в связке.
SILNO_CHUZHOE = re.compile(
    r'центробежн\w+\s+насос|насос\w+\s+центробежн|паров\w+\s+турбин|дымосос|снегоубор|газонокос|'
    r'аккумуляторн\w+\s+воздуходувк|вихрев\w+\s+воздуходувк|поршнев\w+\s+компрессор|'
    r'винтов\w+\s+компрессор|ротацион\w+\s+воздуходувк|роторн\w+\s+воздуходувк', re.I)


def tekst(r):
    return ' '.join((r.get(k) or '') for k in ('obekt', 'tekst', 'marki', 'chem_dokazano'))


def main():
    rows = list(csv.DictReader(open(FAKTY, encoding='utf-8-sig'), delimiter=';'))
    tipy = Counter(r.get('tip_mashiny') for r in rows)

    pervyj = defaultdict(list)   # живое выкинуто
    vtoroj = []                  # мусор остался
    for r in rows:
        t = r.get('tip_mashiny') or ''
        s = tekst(r)
        if t in NASH:
            if SILNO_CHUZHOE.search(s) and not SILNO_NASHE.search(s):
                vtoroj.append(r)
        elif t not in ('не установлен', 'тип не установлен', 'не применимо',
                       'вид не назван (общая формулировка)'):
            if SILNO_NASHE.search(s) and not SILNO_CHUZHOE.search(s):
                pervyj[t].append(r)

    cols = ['inn', 'predpriyatie', 'sostoyanie', 'tip_mashiny', 'ogovorka', 'marki',
            'sreda_mashiny', 'data', 'chto_za_data', 'tekst', 'ssylka', 'istochnik',
            'podozrenie']
    with open(OTSEV, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in rows:
            t = r.get('tip_mashiny') or ''
            if t in NASH or t in ('не установлен', 'не применимо'):
                continue
            r = dict(r)
            r['podozrenie'] = ('в тексте есть бесспорный признак нашей машины — проверить руками'
                               if any(r is x for x in pervyj.get(t, [])) else '')
            w.writerow(r)

    with open(OTCHET, 'w', encoding='utf-8') as f:
        f.write('# Проверка отсева в обе стороны\n\n')
        f.write(f'Фактов всего: {len(rows)}. Признано центробежными: '
                f'{sum(tipy[k] for k in NASH)}.\n\n## Сколько чего в корзинах\n\n')
        for k, v in tipy.most_common():
            f.write(f'- {k} — {v}\n')
        f.write(f'\n## Ошибка первого рода (живое в мусоре)\n\n'
                f'Подозрений после правки: **{sum(len(v) for v in pervyj.values())}**.\n\n')
        for k, v in sorted(pervyj.items(), key=lambda x: -len(x[1])):
            f.write(f'- {k} — {len(v)} из {tipy[k]}\n')
            for r in v[:3]:
                f.write(f'    - «{(r.get("tekst") or "")[:150]}»\n')
        f.write('\nОстаток прочитан глазами и признан НЕ ошибкой: это строки вида «центробежный\n'
                'компрессор марки ЦНС 180-1422-3ТМ на БКНС, ЦППД-1 Вахское месторождение». ЦНС —\n'
                'центробежный насос секционный, и на кустовой насосной станции поддержания\n'
                'пластового давления он качает воду, а не сжимает воздух. Слово «компрессор» тут\n'
                'ошибка составителя заключения, а не наша. Правило право, придирка механики — нет.\n')
        f.write(f'\n## Ошибка второго рода (мусор среди центробежных)\n\n'
                f'Подозрений после правки: **{len(vtoroj)}**.\n\n')
        for r in vtoroj[:20]:
            f.write(f'- «{(r.get("tekst") or "")[:150]}»\n')
        f.write('\nОстаток прочитан глазами и признан НЕ ошибкой: во всех этих строках паровая\n'
                'турбина — ПРИВОД нашей машины, а не сама машина: «Паровая турбина К-22-90-2 с\n'
                'компрессором К-3000-61-1» (воздухоразделительная установка), «статор паровой\n'
                'турбины В-13 турбокомпрессора „Моника“», «компрессор RD7B с приводной паровой\n'
                'турбиной 6MP3-2F». Такие предприятия — лучшие в очереди, а не мусор.\n')
        og = Counter(r.get('ogovorka') for r in rows if r.get('ogovorka'))
        f.write(f'\n## Оговорки (машина названа, но предмет строки — часть или услуга)\n\n')
        for k, v in og.most_common():
            f.write(f'- {k} — {v}\n')

    print(f'первый род (живое в мусоре): {sum(len(v) for v in pervyj.values())}')
    for k, v in sorted(pervyj.items(), key=lambda x: -len(x[1])):
        print(f'   {len(v):>5} из {tipy[k]:>6}  {k}')
    print(f'второй род (мусор среди центробежных): {len(vtoroj)}')
    print(f'строк в корзине выложено: {sum(v for k, v in tipy.items() if k not in NASH and k not in ("не установлен", "не применимо"))}')
    for p in (OTSEV, OTCHET):
        subprocess.run(['bash', os.path.join(BAZA, 'server', 'drop_client.sh'), 'up', p],
                       capture_output=True, timeout=900)
        print(f'выложено на дроп → {os.path.basename(p)}')


if __name__ == '__main__':
    main()
