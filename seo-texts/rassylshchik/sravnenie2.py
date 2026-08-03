# -*- coding: utf-8 -*-
"""Замер судей ЗАНОВО, с temperature=0, и с проверкой воспроизводимости.

Первый замер был одиночным прогоном на модель, и повтор той же конфигурации дал другие числа.
Поэтому здесь порядок обратный: СНАЧАЛА проверяю, что прогон вообще воспроизводим, и только
потом сравниваю модели. Если два одинаковых прогона расходятся — сравнивать нечего, и это
единственный честный вывод, который можно сделать.
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, '/home/user/work')
import proverka_privyazki as P  # noqa: E402

MIS = {0, 11, 12, 13, 20, 22, 25, 40, 44, 45, 52, 54, 58, 59, 62, 63}
pairs = json.load(open('/home/user/work/rassyl/pairs-audit.json', encoding='utf-8'))
# deepseek-v4-pro исключена не по вкусу: 03.08 шлюз отдаёт на неё 404 model_not_found.
MODELI = ['gemini-3.6-flash', 'gemini-3.5-flash', 'gpt-5.4-mini', 'gpt-5.5',
          'claude-haiku-4-5', 'claude-sonnet-5', 'claude-fable-5']


def прогон(model, второе=None, имя=''):
    t0 = time.time()

    def один(p):
        try:
            return P.проверить(p, model=model, второе_мнение=второе)
        except Exception as e:  # noqa: BLE001
            return True, 'сбой', f'{type(e).__name__}: {str(e)[:50]}'
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(один, pairs))
    отпр = [i for i, r in enumerate(res) if r[0]]
    оши = [i for i in отпр if i in MIS]
    задерж = [i for i, r in enumerate(res) if not r[0] and i not in MIS]
    сб = sum(1 for r in res if r[1] == 'сбой')
    print(f'{имя:40} писем {len(отпр):>2} | ошибочных {len(оши)} | поймано {16-len(оши)}/16 | '
          f'зря задержано {len(задерж):>2} | {round(time.time()-t0)}с | сбоев {сб}', flush=True)
    return {'imya': имя, 'model': model, 'vtoroe': второе, 'pisem': len(отпр),
            'oshibochnyh': len(оши), 'poymano': 16 - len(оши), 'zaderzhano': len(задерж),
            'sboev': сб, 'sek': round(time.time() - t0),
            'keep': [bool(r[0]) for r in res], 'ur': [r[1] for r in res]}


itog = []
a = прогон('gemini-3.6-flash', имя='gemini прогон 1 (проверка повтора)')
b = прогон('gemini-3.6-flash', имя='gemini прогон 2 (проверка повтора)')
itog += [a, b]
raz = [i for i in range(len(pairs)) if a['keep'][i] != b['keep'][i]]
print(f'\nРЕШЕНИЯ РАЗОШЛИСЬ на {len(raz)} парах из {len(pairs)}: {raz}\n', flush=True)

for m in MODELI:
    itog.append(прогон(m, имя=f'{m} (temperature=0)'))
itog.append(прогон('gemini-3.6-flash', второе='gpt-5.4-mini',
                   имя='gemini + переспрос gpt-5.4-mini'))
json.dump({'rashozhdenie_povtora': raz, 'progony': itog},
          open('/home/user/work/sravnenie-modeley-t0.json', 'w', encoding='utf-8'),
          ensure_ascii=False)
print('\nсохранено: sravnenie-modeley-t0.json')
