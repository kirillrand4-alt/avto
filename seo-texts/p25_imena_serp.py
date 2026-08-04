# -*- coding: utf-8 -*-
"""P25: найти ФИО ЛПР по поиску «предприятие + должность». Вход для обратного хода.

ПОЧЕМУ ЭТО ПЕРВЫЙ ШАГ, А НЕ ОБРАТНЫЙ ХОД. Стартовый файл поручает 3-й сессии обратный ход по
ФИО. Но обратный ход — это ФИО → номер, а у P25 сбор идёт С НУЛЯ: из 491 предприятия 456 без
единого человека. Искать номер некому, пока нет имени. Значит мой канал начинает с того же
поискового пула, но с другим запросом: не «человек → его номер», а «предприятие + должность →
кто это».

ЧТО БЕРУ И ЧЕГО НЕ БЕРУ, чтобы не делать чужую работу. 2-я сессия идёт по закупочным площадкам
и делает первую двадцатку руками. Я беру места с 21-го и ниже и только поисковый канал.
Пересечение с их методом 3 возможно, поэтому строка об этом идёт в журнал ДО прогона.

ОТКУДА ФОРМЫ ЗАПРОСА. Из ТЗ, раздел «Метод 3», плюс проверенное на центробежке: кавычки
обязательны — без них поиск приносит однофамильцев с других заводов; название берётся и из
ЕГРЮЛ, и коротким видом, потому что «АО „КАУСТИК"» и «Каустик Волгоград» дают разную выдачу.

ЗАСЛОНЫ, БЕЗ КОТОРЫХ КАНАЛ ВРЕДЕН — все три оплачены вчера:

  * ПРИНАДЛЕЖНОСТЬ СТРАНИЦЫ (`chuzhaya_stranica`). Случай Юрина: имя нашлось на приветствии
    выставки, и в панель уехал телефон организатора как номер главного инженера. Страница
    засчитывается, только если это сайт предприятия, страница про него на сайте холдинга,
    карточка закупки или в тексте названо само предприятие;
  * ДОЛЖНОСТЬ БЕЗ ПОДРАЗДЕЛЕНИЯ РОЛЬ НЕ ОПРЕДЕЛЯЕТ. «Заместитель главного инженера по
    экологии» — не первый круг, хотя слова совпадают;
  * ДАТА ПРИНАДЛЕЖИТ НАБЛЮДЕНИЮ. Пишется дата из ТЕКСТА страницы, а не день выгрузки; нет
    даты в тексте — поле пустое, и это честнее выдуманной свежести.

Запуск:
    python3 p25_imena_serp.py --polozhit          # положить канал и список на сервер
    python3 p25_imena_serp.py --ot 21 --do 120    # прогон по местам 21..120
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
import run_on_server as R  # noqa: E402

TUT = os.path.dirname(os.path.abspath(__file__))
SPISOK_LOK = ('/tmp/claude-0/-home-user-avto/66783df1-79e2-513f-8bfb-9c49a1f69007/'
              'scratchpad/P25-PREDPRIYATIYA-po-summe.csv')
KANAL = r'C:\sender\_ops\3s_p25_imena.py'
VHOD = r'C:\sender\_ops\3s_p25_predpriyatiya.csv'
POTOK = r'C:\sender\_ops\p25-imena.jsonl'

SCRIPT = r'''
# -*- coding: utf-8 -*-
import csv, json, os, re, sys, threading, time
sys.path.insert(0, r'C:\sender\_ops')
import _3s_lpr_obratnyy as L          # готовый двухдвижковый serp с ретраями
import _3s_chuzhaya_stranica as CH

VHOD = r'C:\sender\_ops\3s_p25_predpriyatiya.csv'
POTOK = r'C:\sender\_ops\p25-imena.jsonl'
OT = int(sys.argv[sys.argv.index('--ot') + 1]) if '--ot' in sys.argv else 21
DO = int(sys.argv[sys.argv.index('--do') + 1]) if '--do' in sys.argv else 120
POT = int(sys.argv[sys.argv.index('--potokov') + 1]) if '--potokov' in sys.argv else 6

# ДОЛЖНОСТИ ПЕРВОГО И ВТОРОГО КРУГА. Третий (закупки) не спрашиваем: по ТЗ он ниже, а канал
# общий и узкий — тратить его на снабженцев, пока не пройдены технические, значит менять
# главную меру на второстепенную.
DOLZHNOSTI = ('главный инженер', 'главный механик', 'главный энергетик',
              'технический директор', 'начальник производства')

FIO = re.compile(
    r'\b([А-ЯЁ][а-яё]{2,}(?:-[А-ЯЁ][а-яё]{2,})?)\s+'
    r'([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ][а-яё]{3,}(?:ович|евич|ьевич|инич|овна|евна|ьевна|ична))\b')
FIO_OBR = re.compile(
    r'\b([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ][а-яё]{3,}(?:ович|евич|ьевич|инич|овна|евна|ьевна|ична))\s+'
    r'([А-ЯЁ][а-яё]{2,}(?:-[А-ЯЁ][а-яё]{2,})?)\b')          # «Эдуард Юрьевич Еремеев»
# Дата ИЗ ТЕКСТА, а не день выгрузки.
DATA = re.compile(r'\b(20[0-2]\d)\s*(?:год|г\.)?|\b\d{1,2}\.\d{2}\.(20[0-2]\d)\b')
# Слова, отменяющие первый круг: должность есть, а зона не наша.
NE_NASH_KRUG = re.compile(r'по\s+эколог|эколог|охран\w+\s+труд|промышленн\w+\s+безопасн|'
                          r'по\s+кадр|по\s+персонал|по\s+социальн|по\s+режим|'
                          r'по\s+граждан\w+\s+оборон|по\s+связям', re.I)


def korotkoe(imya):
    """«ООО "КОМПРЕССОР-ТЕХЦЕНТР"» → «КОМПРЕССОР-ТЕХЦЕНТР»."""
    v = re.sub(r'^\s*(ООО|ОАО|ЗАО|ПАО|АО|НАО|ФГУП|ГУП|МУП|ФКП|ИП)\s+', '', (imya or '').strip())
    return v.strip('"«» ')


def razobrat(docs, predpr, dolzh):
    """Из выдачи — люди с должностью, ссылкой и датой из текста."""
    out = []
    for d in docs:
        url = (d.get('url') or '').strip()
        tekst = ' '.join(str(d.get(k) or '') for k in ('title', 'passage', 'snippet', 'text'))
        if not tekst.strip():
            continue
        # ЗАСЛОН ПРИНАДЛЕЖНОСТИ — до разбора, а не после: иначе имя уже «найдено».
        est, poch = CH.stranica_podtverzhdaet(url, '', predpr, tekst)
        okno = tekst
        for m in list(FIO.finditer(okno)) + list(FIO_OBR.finditer(okno)):
            fio = m.group(0)
            # Должность рядом: окно ±120 знаков, иначе имя со страницы «наши люди» получит
            # чужую должность из соседнего абзаца.
            ryad = okno[max(0, m.start() - 120):m.end() + 120]
            if dolzh.split()[0][:6].lower() not in ryad.lower():
                continue
            if NE_NASH_KRUG.search(ryad):
                out.append({'fio': fio, 'dolzhnost': dolzh, 'krug': 'мимо: зона не наша',
                            'ssylka': url, 'podtverzhdena': est, 'pochemu': poch[:110],
                            'citata': ryad[:300], 'data_iz_teksta': ''})
                continue
            dm = DATA.search(ryad)
            out.append({'fio': fio, 'dolzhnost': dolzh,
                        'krug': '1-2 круг' if est else 'страница не подтверждает',
                        'ssylka': url, 'podtverzhdena': est, 'pochemu': poch[:110],
                        'citata': ryad[:300],
                        'data_iz_teksta': (dm.group(1) or dm.group(2)) if dm else ''})
    return out


stroki = [r for r in csv.DictReader(open(VHOD, encoding='utf-8-sig'))
          if OT <= int(r['mesto']) <= DO and r.get('tip') != 'ИП']
gotovo = set()
if os.path.exists(POTOK):
    for ln in open(POTOK, encoding='utf-8'):
        try:
            z = json.loads(ln)
        except Exception:
            continue
        if not z.get('err'):
            gotovo.add((z['inn'], z['dolzhnost']))

zad = [(r, d) for r in stroki for d in DOLZHNOSTI if (r['inn'], d) not in gotovo]
print('предприятий %d, запросов к обходу %d, потоков %d' % (len(stroki), len(zad), POT),
      file=sys.stderr, flush=True)

f = open(POTOK, 'a', encoding='utf-8')
lock = threading.Lock()
sch = {'n': 0, 'sboev': 0, 'lyudey': 0, 'podtv': 0}


def odin(z):
    r, dolzh = z
    polnoe, kratko = r['naimenovanie'].strip('"'), korotkoe(r['naimenovanie'])
    zapros = '"%s" "%s"' % (kratko, dolzh)
    docs, err = L.serp(zapros)
    if err and not docs:
        zapis = {'inn': r['inn'], 'predpriyatie': polnoe, 'dolzhnost': dolzh, 'err': err}
    else:
        lyudi = razobrat(docs, polnoe, dolzh)
        zapis = {'inn': r['inn'], 'predpriyatie': polnoe, 'dolzhnost': dolzh,
                 'zapros': zapros, 'naydeno': len(docs), 'lyudi': lyudi}
    with lock:
        f.write(json.dumps(zapis, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())          # правило долговечности: результат переживает откат
        sch['n'] += 1
        if zapis.get('err'):
            sch['sboev'] += 1
        else:
            sch['lyudey'] += len(zapis['lyudi'])
            sch['podtv'] += len([x for x in zapis['lyudi'] if x['podtverzhdena']])
        if sch['n'] % 25 == 0:
            print('  %d/%d запросов, людей %d (подтверждённой страницей %d), сбоев %d'
                  % (sch['n'], len(zad), sch['lyudey'], sch['podtv'], sch['sboev']),
                  file=sys.stderr, flush=True)


potoki = []
for z in zad:
    while len([t for t in potoki if t.is_alive()]) >= POT:
        time.sleep(0.15)
    t = threading.Thread(target=odin, args=(z,), daemon=True)
    t.start(); potoki.append(t)
for t in potoki:
    t.join()
f.close()
print('готово: запросов %d, ЛЮДЕЙ %d, из них страница подтверждает %d, СБОЕВ %d '
      '(сбой это не ноль) -> %s' % (sch['n'], sch['lyudey'], sch['podtv'], sch['sboev'], POTOK),
      file=sys.stderr, flush=True)
'''


def main():
    if '--polozhit' in sys.argv:
        fajly = [
            {'dest': r'C:\sender\_ops\_3s_lpr_obratnyy.py',
             'b64': base64.b64encode(open(os.path.join(TUT, 'lpr_obratnyy.py'),
                                          encoding='utf-8').read().encode()).decode()},
            {'dest': r'C:\sender\_ops\_3s_chuzhaya_stranica.py',
             'b64': base64.b64encode(open(os.path.join(TUT, 'chuzhaya_stranica.py'),
                                          encoding='utf-8').read().encode()).decode()},
            {'dest': VHOD, 'b64': base64.b64encode(open(SPISOK_LOK, 'rb').read()).decode()},
            {'dest': KANAL, 'b64': base64.b64encode(SCRIPT.encode()).decode()},
        ]
        R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': fajly}, timeout=300)
        print('положено', file=sys.stderr)
        return
    argv = []
    for k in ('--ot', '--do', '--potokov'):
        if k in sys.argv:
            argv += [k, sys.argv[sys.argv.index(k) + 1]]
    r = R.submit('enrich_contacts',
                 {'op': 'panel_py', 'script': KANAL, 'argv': argv, 'timeout': 1700},
                 timeout=1800)
    d = r.get('data') or {}
    print((d.get('stdout_tail') or '')[-1500:])
    print('--- ход ---\n' + (d.get('stderr_tail') or '')[-2500:], file=sys.stderr)


if __name__ == '__main__':
    main()
