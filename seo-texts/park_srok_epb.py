# -*- coding: utf-8 -*-
"""СРОК действия заключения ЭПБ — со страницы самого заключения.

ЗАЧЕМ. Проверка 25 ссылок глазами показала: «Действует до 31.12.2030» / «Срок истёк
25.04.2022» стоит прямым текстом на 22 страницах из 25, а у меня колонка пуста в 93 %
строк — в списке реестра её нет, она только в карточке. Это самая продажная колонка:
экспертиза кончилась — машину продлевать или менять.

ПОСЛЕДОВАТЕЛЬНО, БЕЗ ПАРАЛЛЕЛИ. Тот же заход показал: `monitor-pb.ru` при трёх потоках
отдаёт `ERR_CONNECTION_RESET` — заглушку на 195 знаков, которая выглядит как «страница
не открылась». Одна нить с паузой открывает те же страницы с первой попытки.

Порядок целей: сначала машины (не узлы) с заводским номером — по ним письмо предметнее.
"""
import csv, json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mpb_po_inn as M

L = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engineers-lens')
VHOD = os.path.join(L, 'PARK-FAKTY-2S-EPB-POLNYE.csv')
POTOK = os.path.join(L, 'PARK-SROK-EPB-2S.jsonl')
PAUZA = float(os.environ.get('PAUZA', '1.0'))
PREDEL = int(os.environ.get('PREDEL', '4000'))

SROK = re.compile(r'(?:действует\s+до|срок\s+действия\s*[:—-]?\s*(?:до)?|действительно\s+до)'
                  r'\s*([0-3]?\d\.[01]?\d\.\d{4})', re.I)
ISTEK = re.compile(r'срок\s+исте[кч]\w*\s*([0-3]?\d\.[01]?\d\.\d{4})', re.I)
NE_UKAZAN = re.compile(r'срок\s+действия\s+не\s+указан', re.I)


def main():
    rows = list(csv.DictReader(open(VHOD, encoding='utf-8-sig'), delimiter=';'))
    gotovo = set()
    if os.path.exists(POTOK):
        for ln in open(POTOK, encoding='utf-8'):
            try:
                gotovo.add(json.loads(ln)['ssylka'])
            except (json.JSONDecodeError, KeyError):
                pass
    celi, vidno = [], set()
    for x in sorted(rows, key=lambda r: (r['tip'].startswith('узел'), not r['zavodskoy_nomer'])):
        u = x['ssylka']
        if not u.startswith('http') or u in gotovo or u in vidno:
            continue
        vidno.add(u)
        celi.append(x)
    celi = celi[:PREDEL]
    print(f'страниц к обходу: {len(celi)} (уже пройдено {len(gotovo)})', file=sys.stderr, flush=True)
    f = open(POTOK, 'a', encoding='utf-8')
    sch = {'страниц': 0, 'срок найден': 0, 'истёк': 0, 'не указан': 0, 'не открылась': 0}
    for n, x in enumerate(celi, 1):
        h = M._vzyat(x['ssylka'], popytok=3)
        if h.startswith('__ОШИБКА__') or len(h) < 800:
            sch['не открылась'] += 1
            f.write(json.dumps({'ssylka': x['ssylka'], 'err': h[:70]}, ensure_ascii=False) + '\n')
        else:
            t = M._bez_tegov(h)
            m, i = SROK.search(t), ISTEK.search(t)
            srok = (m.group(1) if m else (i.group(1) if i else ''))
            status = 'истёк' if i else ('действует' if m else
                                        ('срок не указан в реестре' if NE_UKAZAN.search(t) else ''))
            sch['страниц'] += 1
            if srok:
                sch['срок найден'] += 1
            if i:
                sch['истёк'] += 1
            if status.startswith('срок не указан'):
                sch['не указан'] += 1
            j = t.find('ействует до') if m else (t.find('рок исте') if i else -1)
            f.write(json.dumps({'ssylka': x['ssylka'], 'inn': x['inn'],
                                'nomer': x['nomer_zaklucheniya'], 'srok_do': srok,
                                'status': status,
                                'citata': ' '.join(t[max(0, j - 60):j + 90].split())[:180] if j >= 0 else ''},
                               ensure_ascii=False) + '\n')
        f.flush()
        if n % 50 == 0:
            print(f'  {n}/{len(celi)}: {sch}', file=sys.stderr, flush=True)
        time.sleep(PAUZA)
    print(f'готово: {sch}', file=sys.stderr)


main()
