# -*- coding: utf-8 -*-
"""Замер заслона на размеченных 66 парах. Печатает то, чем меряют: письма, ошибочные,
пойманные мисматчи, зря задержанные. Запускать после любой правки proverka_privyazki."""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, '/home/user/work')
import proverka_privyazki as P  # noqa: E402

MIS = {0, 11, 12, 13, 20, 22, 25, 40, 44, 45, 52, 54, 58, 59, 62, 63}
pairs = json.load(open('/home/user/work/rassyl/pairs-audit.json', encoding='utf-8'))


def прогон(model=None, второе=P.ВТОРОЕ_МНЕНИЕ, имя=''):
    t0 = time.time()

    def один(p):
        try:
            return P.проверить(p, model=model, второе_мнение=второе)
        except Exception as e:  # noqa: BLE001
            return True, 'сбой', f'{type(e).__name__}: {str(e)[:60]}'
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(один, pairs))
    отпр = [i for i, r in enumerate(res) if r[0]]
    оши = [i for i in отпр if i in MIS]
    задерж = [i for i, r in enumerate(res) if not r[0] and i not in MIS]
    print(f'{имя:36} писем {len(отпр):>2} | ошибочных {len(оши)} | '
          f'поймано {16 - len(оши)}/16 | зря задержано {len(задерж):>2} | '
          f'{round(time.time() - t0)}с | сбоев {sum(1 for r in res if r[1] == "сбой")}', flush=True)
    return res


if __name__ == '__main__':
    прогон(второе=None, имя='deepseek один (было)')
    r = прогон(имя=f'deepseek + переспрос {P.ВТОРОЕ_МНЕНИЕ}')
    json.dump([{'i': i, 'keep': x[0], 'ur': x[1], 'prichina': x[2]} for i, x in enumerate(r)],
              open('/home/user/work/zamer-zaslona.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
