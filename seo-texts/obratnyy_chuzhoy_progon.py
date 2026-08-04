# -*- coding: utf-8 -*-
"""Обратный ход по чужому списку на сервере, кусками.

ЗАЧЕМ ОТДЕЛЬНЫЙ ГОНЩИК. Ключи XMLRiver лежат на сервере, задание раннера умирает на 1700 с, а
фоновые процессы в песочнице между ходами не живут — проверено трижды (nohup, setsid+disown,
фон гарнизона). Значит длинный список гонится кусками, и каждый кусок — отдельное задание.
Возобновление берёт на себя сам канал: он читает свой поток `lpr-obratnyy-chuzhoy.jsonl` и
пропускает уже спрошенных, а записи со сбоем пройденными НЕ считает.

ВХОД: файл 2-й сессии `DLYA-3S-FIO-s-kartochek-bez-lichnogo.csv` — 1 051 человек с карточек
закупок, у которых имя полное, а личного мобильного нет (31 без номера вовсе, 1 020 с общим
или городским). Полных ФИО из них 869 на 190 предприятиях; остальные отсеяны заслоном
инициалов — «Иванов И.И.» в кавычках находит однофамильцев по всей стране.

Запуск:
    python3 obratnyy_chuzhoy_progon.py --polozhit      # положить канал и список на сервер
    python3 obratnyy_chuzhoy_progon.py --lim 200       # один кусок
    python3 obratnyy_chuzhoy_progon.py --svodka        # что уже добыто
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
import run_on_server as R  # noqa: E402

TUT = os.path.dirname(os.path.abspath(__file__))
SPISOK = ('/tmp/claude-0/-home-user-avto/66783df1-79e2-513f-8bfb-9c49a1f69007/scratchpad/'
          'DLYA-3S-FIO-s-kartochek-bez-lichnogo.csv')
KANAL = r'C:\sender\_ops\3s_lpr_obratnyy.py'
VHOD = r'C:\sender\_ops\3s_spisok_2s.csv'
POTOK = r'C:\sender\_ops\lpr-obratnyy-chuzhoy.jsonl'

SVODKA = r'''
import collections, json, os, re, sys
POTOK = r'C:\sender\_ops\lpr-obratnyy-chuzhoy.jsonl'
sch = collections.Counter()
lyudi, tel_lichnyh = 0, 0
if os.path.exists(POTOK):
    for ln in open(POTOK, encoding='utf-8'):
        try:
            z = json.loads(ln)
        except Exception:
            continue
        lyudi += 1
        if z.get('err'):
            sch['сбой: ' + str(z['err'])[:60]] += 1
            continue
        kont = z.get('kontakty') or []
        tel = [k for k in kont if k.get('vid') == 'телефон' or re.search(r'\d{7}', str(k.get('znachenie', '')))]
        mob = [k for k in tel if re.sub(r'\D', '', str(k.get('znachenie', '')))[-10:].startswith('9')]
        sch['спрошено'] += 1
        if tel:
            sch['с телефоном'] += 1
        if mob:
            sch['из них мобильный'] += 1
            tel_lichnyh += len(mob)
        if not kont:
            sch['контактов не нашлось'] += 1
for k, v in sorted(sch.items(), key=lambda x: -x[1]):
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({'строк_в_потоке': lyudi, 'мобильных_номеров': tel_lichnyh},
                           ensure_ascii=False))
'''


def polozhit():
    fajly = [{'dest': KANAL, 'b64': base64.b64encode(
        open(os.path.join(TUT, 'lpr_obratnyy.py'), encoding='utf-8').read().encode()).decode()},
        {'dest': VHOD, 'b64': base64.b64encode(open(SPISOK, 'rb').read()).decode()}]
    R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': fajly}, timeout=300)
    print(f'положено: {KANAL} и {VHOD}', file=sys.stderr)


def kusok(lim, potokov):
    r = R.submit('enrich_contacts',
                 {'op': 'panel_py', 'script': KANAL,
                  'argv': ['--vhod-csv', VHOD, '--potok', POTOK,
                           '--lim', str(lim), '--potokov', str(potokov)],
                  'timeout': 1700}, timeout=1800)
    d = r.get('data') or {}
    print((d.get('stdout_tail') or '')[-2500:])
    err = (d.get('stderr_tail') or '')
    if err:
        print('--- stderr ---\n' + err[-2500:], file=sys.stderr)


def svodka():
    dest = r'C:\sender\_ops\3s_obratnyy_svodka.py'
    R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': [
        {'dest': dest, 'b64': base64.b64encode(SVODKA.encode()).decode()}]}, timeout=300)
    r = R.submit('enrich_contacts', {'op': 'panel_py', 'script': dest, 'argv': [],
                                     'timeout': 600}, timeout=900)
    d = r.get('data') or {}
    for s in (d.get('stdout_tail') or '').splitlines():
        s = s.strip()
        if s.startswith('REC '):
            print(s[4:].replace('\t', '  ×'))
        elif s.startswith('ИТОГ '):
            print(json.dumps(json.loads(s[5:]), ensure_ascii=False))


if __name__ == '__main__':
    if '--polozhit' in sys.argv:
        polozhit()
    if '--svodka' in sys.argv:
        svodka()
    elif '--lim' in sys.argv:
        kusok(int(sys.argv[sys.argv.index('--lim') + 1]),
              int(sys.argv[sys.argv.index('--potokov') + 1]) if '--potokov' in sys.argv else 6)
