# -*- coding: utf-8 -*-
r"""Заставить работника ЗАБЫТЬ вердикт «неясно» по названным адресам.

Работник отсеивает уже проверенное по своему локальному probe-rezultat.jsonl:
адрес, однажды получивший ответ, он больше не трогает. Для «неясно» это плохо —
вердикт не про адрес, а про обстоятельства (серый список, обрыв связи), и его
надо переспрашивать. Здесь вырезаем такие строки, чтобы следующий проход
проверил адреса заново.

Вырезанное не выбрасываем: складываем в архив рядом и на дроп — по нему видно,
что и когда было забыто.

    python vps_zabyt_neyasno.py <файл-со-списком-на-дропе>
    python vps_zabyt_neyasno.py --vse           забыть ВСЕ «неясно»
"""
import json
import os
import sys
import time
import urllib.request

# Раннер кладёт присланные скрипты в подпапку _ops, а журнал работника лежит
# уровнем выше, рядом с самим probe_worker.py. Поэтому ищем, а не гадаем.
_ЗДЕСЬ = os.path.dirname(os.path.abspath(__file__))
КОР = _ЗДЕСЬ
for _к in (_ЗДЕСЬ, os.path.dirname(_ЗДЕСЬ), r'C:\probe', r'C:\sender\probe'):
    if os.path.exists(os.path.join(_к, 'probe-rezultat.jsonl')):
        КОР = _к
        break
МЕСТНЫЙ = os.path.join(КОР, 'probe-rezultat.jsonl')
АРХИВ = os.path.join(КОР, 'probe-rezultat-zabyto.jsonl')
ЗАБЫТЬ = 'неясно'


def _env():
    из = dict(os.environ)
    п = next((x for x in (os.path.join(_к, 'runner-secrets.env')
                          for _к in (КОР, _ЗДЕСЬ, os.path.dirname(_ЗДЕСЬ)))
              if os.path.exists(x)), '')
    if п and os.path.exists(п):
        for l in open(п, encoding='utf-8', errors='replace'):
            if '=' in l and not l.strip().startswith('#'):
                k, v = l.split('=', 1)
                из.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return из


def _дроп(метод, имя, данные=None):
    e = _env()
    req = urllib.request.Request('%s/%s' % (e['DROP_URL'].rstrip('/'), имя),
                                 data=данные, method=метод)
    req.add_header('X-Drop-Token', e['DROP_TOKEN'])
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    все = '--vse' in sys.argv
    список = None
    доводы = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not все:
        if not доводы:
            print(json.dumps({'error': 'не сказано, какие адреса забыть'},
                             ensure_ascii=False))
            return 2
        список = {str(a).strip().lower()
                  for a in json.loads(_дроп('GET', доводы[0]).decode('utf-8'))}
    if not os.path.exists(МЕСТНЫЙ):
        print(json.dumps({'error': 'локального журнала нет', 'путь': МЕСТНЫЙ},
                         ensure_ascii=False))
        return 1
    оставим, забыто = [], []
    with open(МЕСТНЫЙ, encoding='utf-8', errors='replace') as f:
        for л in f:
            if not л.strip():
                continue
            try:
                d = json.loads(л)
            except Exception:  # noqa: BLE001  битую строку не теряем
                оставим.append(л.rstrip('\n'))
                continue
            адрес = str(d.get('email') or '').lower()
            if d.get('verdict') == ЗАБЫТЬ and (все or адрес in список):
                забыто.append(л.rstrip('\n'))
            else:
                оставим.append(л.rstrip('\n'))
    if забыто:
        with open(АРХИВ, 'a', encoding='utf-8') as f:
            f.write('\n'.join(забыто) + '\n')
            f.flush()
            os.fsync(f.fileno())
        врем = МЕСТНЫЙ + '.new'
        with open(врем, 'w', encoding='utf-8') as f:
            f.write('\n'.join(оставим) + ('\n' if оставим else ''))
            f.flush()
            os.fsync(f.fileno())
        os.replace(врем, МЕСТНЫЙ)
        # зеркало на дроп: панель читает результат оттуда
        with open(МЕСТНЫЙ, 'rb') as f:
            _дроп('PUT', 'probe-rezultat.jsonl', f.read())
        _дроп('PUT', 'probe-rezultat-zabyto.jsonl',
              ('\n'.join(забыто) + '\n').encode('utf-8'))
    print(json.dumps({'было_строк': len(оставим) + len(забыто),
                      'забыто': len(забыто), 'осталось': len(оставим),
                      'ts': time.strftime('%Y-%m-%dT%H:%M:%S')},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
