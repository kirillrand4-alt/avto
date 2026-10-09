# -*- coding: utf-8 -*-
r"""Дозаразметка контактов (09.10, полный прогон Meyer): у номеров и почт с подписью рядом (ФИО, должность, отдел), которым
обход не дал роль — модель не ответила (шлюз рвал TLS при 48 потоках; разметка прошла у 41% против 92% на пробе), —
разметка заново по сохранённому фрагменту страницы, без повторного обхода. Тот же промпт обхода (ПРОМПТ_НОМЕРА), куски
по 14 контактов. Итог — новая запись компании в <набор>-kontakty.jsonl: копия последней с дозаполненными полями и
отметкой «дозаразметка» (Excel и проверки берут последнюю запись). Резюм: компании, у которых всё размечено,
пропускаются. Запускать, когда обход этого набора не идёт (один файл) — в волнах после обхода.
"""
import io
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import kc_kontakty as KK  # noqa: E402
import cc_obhod as CO  # noqa: E402
import meyer_nalichie as MN  # noqa: E402

НАБОР = os.environ.get('KC_NABOR', 'pilot')
ВЫХОД = os.path.join(DIR, НАБОР + '-kontakty.jsonl')
_лок = threading.Lock()


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def нужно(н):
    return not (н.get('класс') or н.get('роль')) and bool(CO.ПОДПИСЬ.search((н.get('контекст') or '')[-260:]))


def одна(з, имя):
    номера = з.get('номера') or []
    цели = [j for j, н in enumerate(номера) if нужно(н)]
    размечено = 0
    for k in range(0, len(цели), 14):
        кусок = цели[k:k + 14]
        текст = '\n…\n'.join((номера[j].get('контекст') or '')[-500:] for j in кусок)
        ответ = KK.модель(KK.ПРОМПТ_НОМЕРА.format(
            домен=MN.домен(з.get('сайт') or ''), название=имя, url=(номера[кусок[0]].get('страницы') or [''])[0],
            текст=текст[:6500], номера='\n'.join('%d. %s' % (n + 1, номера[j].get('номер') or номера[j].get('почта'))
                                                for n, j in enumerate(кусок))), True)
        for n, j in enumerate(кусок):
            x = ответ.get(n + 1) or {}
            if not x:
                continue
            н = номера[j]
            н.update({'фио': н.get('фио') or (x.get('фио') or '')[:80],
                      'должность': н.get('должность') or (x.get('должность') or '')[:120],
                      'класс': x.get('класс') if x.get('класс') in KK.КЛАССЫ else '',
                      'роль': x.get('роль') if x.get('роль') in KK.РОЛИ else '',
                      'лпр': x.get('лпр') if x.get('лпр') in ('да', 'возможно', 'нет') else '',
                      'почему': (x.get('почему') or '')[:100],
                      'чей': x.get('чей') if x.get('чей') in ('эта', 'другая') else ''})
            размечено += bool(н['класс'] or н['роль'])
    if размечено:
        записать(dict(з, номера=номера, дозаразметка=time.strftime('%Y-%m-%d %H:%M')))
    return len(цели), размечено


def main():
    сп = json.load(io.open(os.path.join(DIR, НАБОР + '-spisok.json'), encoding='utf-8'))['компании']
    посл = {}
    for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('inn'):
            посл[з['inn']] = з
    задачи = [з for з in посл.values() if з.get('итог') == 'ok' and any(нужно(н) for н in з.get('номера') or [])]
    print('компаний к дозаразметке', len(задачи), 'контактов', sum(sum(1 for н in з['номера'] if нужно(н)) for з in задачи),
          flush=True)
    сч = {'целей': 0, 'размечено': 0}
    n = [0]

    def шаг(з):
        ц, р = одна(з, (сп.get(з['inn']) or {}).get('имя') or з['inn'])
        with _лок:
            сч['целей'] += ц
            сч['размечено'] += р
            n[0] += 1
            if n[0] % 50 == 0:
                print('готово %d/%d' % (n[0], len(задачи)), json.dumps(сч, ensure_ascii=False), flush=True)

    with ThreadPoolExecutor(int(os.environ.get('KC_POTOKOV_SHAGA', '12'))) as ex:
        list(ex.map(шаг, задачи))
    print('готово', json.dumps(сч, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
