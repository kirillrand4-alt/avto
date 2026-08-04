# -*- coding: utf-8 -*-
"""Обратный ход P25: 369 человек с именем, но без личного мобильного.

ВХОД собирает `p25_obratnyy_vhod.py` на сервере из двух списков — 251 имени 2-й сессии с
карточек ЭТП ГПБ и 258 моих кандидатов из поискового канала — и подставляет имя предприятия
из `p25.db` (`company.predpriyatie` по `company.inn`, 491 запись, ни одного промаха по ИНН).
Замер сборки: прочитано 509 строк, в обход 369, отсеяно 40 (личный мобильный уже есть),
25 (неполное ФИО) и 75 дублей — то есть 75 человек названы ОБОИМИ каналами независимо.

ПОЧЕМУ ОТДЕЛЬНЫЙ ПОТОК, А НЕ ОБЩИЙ С ЦЕНТРОБЕЖКОЙ. Провенанс не смешивается: завтра надо
уметь ответить, чей человек и из какого списка пришёл. Поток — `p25-obratnyy.jsonl`.

ЧТО ЭТОТ ПРОГОН ЗАКРЫВАЕТ СРАЗУ ДВЕ ДЫРЫ. Для людей 2-й сессии он ищет личный номер (у них
номер площадочный или городской). Для моих 258 кандидатов он ищет ещё и первоисточник:
страница, на которой рядом с фамилией стоит номер, — это, как правило, сайт предприятия или
карточка закупки, то есть ровно то подтверждение, которого им не хватает.

Запуск:
    python3 p25_obratnyy_progon.py --vhod          # пересобрать вход на сервере
    python3 p25_obratnyy_progon.py --lim 150 --potokov 6
    python3 p25_obratnyy_progon.py --svodka
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
import run_on_server as R  # noqa: E402

TUT = os.path.dirname(os.path.abspath(__file__))
KANAL = r'C:\sender\_ops\3s_lpr_obratnyy.py'
SBOR = r'C:\sender\_ops\3s_p25_obratnyy_vhod.py'
VHOD = r'C:\sender\_ops\3s_p25_obratnyy_vhod.csv'
POTOK = r'C:\sender\_ops\p25-obratnyy.jsonl'

SVODKA = r'''
import collections, json, os, re
POTOK = r'C:\sender\_ops\p25-obratnyy.jsonl'
sch = collections.Counter()
mob, lyudi_s_mob = 0, set()
if os.path.exists(POTOK):
    for ln in open(POTOK, encoding='utf-8'):
        try:
            z = json.loads(ln)
        except Exception:
            continue
        if z.get('err'):
            sch['сбой: ' + str(z['err'])[:50]] += 1
            continue
        sch['спрошено'] += 1
        kont = z.get('kontakty') or []
        tel = [k for k in kont if k.get('tip') == 'телефон']
        lich = [k for k in tel
                if re.sub(r'\D', '', str(k.get('znachenie', '')))[-10:].startswith('9')]
        if tel:
            sch['с телефоном'] += 1
        if lich:
            sch['С ЛИЧНЫМ МОБИЛЬНЫМ'] += 1
            mob += len(lich)
            lyudi_s_mob.add(z['inn'] + '|' + z['fio'])
        if any(k.get('tip') == 'почта' for k in kont):
            sch['с почтой'] += 1
        if not kont:
            sch['контактов не нашлось'] += 1
for k, v in sorted(sch.items(), key=lambda x: -x[1]):
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({'личных_номеров': mob, 'людей_с_личным': len(lyudi_s_mob)},
                           ensure_ascii=False))
'''


def polozhit_sbor():
    R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': [
        {'dest': SBOR, 'b64': base64.b64encode(
            open(os.path.join(TUT, 'p25_obratnyy_vhod.py'), 'rb').read()).decode()}]},
        timeout=300)
    r = R.submit('enrich_contacts', {'op': 'panel_py', 'script': SBOR, 'argv': [],
                                     'timeout': 600}, timeout=900)
    print(((r.get('data') or {}).get('stdout_tail') or '')[-3000:])


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
    dest = r'C:\sender\_ops\3s_p25_obratnyy_svodka.py'
    R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': [
        {'dest': dest, 'b64': base64.b64encode(SVODKA.encode()).decode()}]}, timeout=300)
    r = R.submit('enrich_contacts', {'op': 'panel_py', 'script': dest, 'argv': [],
                                     'timeout': 600}, timeout=900)
    for s in (((r.get('data') or {}).get('stdout_tail')) or '').splitlines():
        s = s.strip()
        if s.startswith('REC '):
            print(s[4:].replace('\t', '  ×'))
        elif s.startswith('ИТОГ '):
            print(json.dumps(json.loads(s[5:]), ensure_ascii=False))


if __name__ == '__main__':
    if '--vhod' in sys.argv:
        polozhit_sbor()
    if '--svodka' in sys.argv:
        svodka()
    elif '--lim' in sys.argv:
        kusok(int(sys.argv[sys.argv.index('--lim') + 1]),
              int(sys.argv[sys.argv.index('--potokov') + 1]) if '--potokov' in sys.argv else 6)
