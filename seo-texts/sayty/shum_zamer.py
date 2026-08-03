# -*- coding: utf-8 -*-
"""Разброс прогона и выбор судьи ПОВТОРАМИ, а не одиночным прогоном.

Замер 03.08: два одинаковых прогона (temperature=0) разошлись в решениях по 5 парам из 66.
Значит «поймал 15 из 16» и «16 из 16» — неразличимы по одному прогону. Здесь каждая связка
гоняется трижды и печатается ДИАПАЗОН.
"""
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, '/home/user/work')
import proverka_privyazki as P  # noqa: E402

MIS = {0, 11, 12, 13, 20, 22, 25, 40, 44, 45, 52, 54, 58, 59, 62, 63}
pairs = json.load(open('/home/user/work/rassyl/pairs-audit.json', encoding='utf-8'))


def прогон(model, второе, имя):
    t0 = time.time()

    def один(p):
        try:
            return P.проверить(p, model=model, второе_мнение=второе)
        except Exception as e:  # noqa: BLE001
            return False, 'сбой', f'{type(e).__name__}'
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(один, pairs))
    отпр = [i for i, r in enumerate(res) if r[0]]
    оши = [i for i in отпр if i in MIS]
    сбоев = sum(1 for r in res if 'сбой' in r[1])
    д = {'pisem': len(отпр), 'oshibochnyh': len(оши), 'poymano': 16 - len(оши),
         'sboev': сбоев, 'sek': round(time.time() - t0)}
    print(f'{имя:44} писем {д["pisem"]:>2} | ошибочных {д["oshibochnyh"]} | '
          f'поймано {д["poymano"]}/16 | сбоев {сбоев} | {д["sek"]}с', flush=True)
    return д


СВЯЗКИ = [('gemini-3.6-flash', None), ('gpt-5.4-mini', None),
          ('gpt-5.4-mini', 'gemini-3.6-flash')]
итог = []
for model, второе in СВЯЗКИ:
    имя = model + (f' + переспрос {второе}' if второе else '')
    п = [прогон(model, второе, f'{имя} [{i+1}/3]') for i in range(3)]
    оши = [x['oshibochnyh'] for x in п]
    пойм = [x['poymano'] for x in п]
    пис = [x['pisem'] for x in п]
    итог.append({'svyazka': имя, 'progony': п, 'oshibochnyh': оши, 'poymano': пойм, 'pisem': пис})
    print(f'  ИТОГ {имя}: ошибочных {min(оши)}–{max(оши)} (среднее {statistics.mean(оши):.1f}), '
          f'поймано {min(пойм)}–{max(пойм)}, писем {min(пис)}–{max(пис)}\n', flush=True)
json.dump(итог, open('/home/user/work/shum-zamer.json', 'w', encoding='utf-8'), ensure_ascii=False)
