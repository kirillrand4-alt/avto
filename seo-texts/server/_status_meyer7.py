# -*- coding: utf-8 -*-
"""Статус полного прогона Meyer (набор meyer7): строки журналов, шаги конвейера, хвосты логов набора, живые процессы
конвейера (любого набора — чтобы стоп не задел чужое), баланс xmlriver."""
import glob
import json
import os
import subprocess
import urllib.request

DIR = r'C:\sender\server'
НАБОР = 'meyer7'
o = {}
for х in ('-serp.jsonl', '-razbor.jsonl', '-spisok.json', '-sayty-dobor.jsonl', '-kontakty.jsonl', '-dop.jsonl',
          '-pasport.jsonl', '-audit.jsonl', '-audit2.jsonl', '-sayt-proverka.jsonl', '-oprov.jsonl', '-glubokiy.jsonl',
          '-glubokiy2.jsonl', '-reestr.json', '-zenka.json'):
    ф = os.path.join(DIR, НАБОР + х)
    if os.path.exists(ф):
        o[х] = sum(1 for _ in open(ф, encoding='utf-8', errors='replace'))
ф = os.path.join(DIR, НАБОР + '-serp.jsonl')
if os.path.exists(ф):
    ош = всего = 0
    for s in open(ф, encoding='utf-8', errors='replace'):
        всего += 1
        ош += '"итог": "ошибка"' in s
    o['serp_ошибок'] = '%d из %d' % (ош, всего)
ф = os.path.join(DIR, НАБОР + '-konveyer.json')
if os.path.exists(ф):
    к = json.load(open(ф, encoding='utf-8'))
    o['конвейер'] = {ш: '%s→%s код %s' % (v.get('старт', ''), v.get('конец', ''), v.get('код', '')) for ш, v in к.get('шаги', {}).items()}
    o['конвейер_ждёт'] = к.get('ждём', '')
    o['волна'] = к.get('волна', '')
    o['фон'] = к.get('фон', {})
    o['конвейер_сырой'] = {ш: {кк: vv for кк, vv in v.items() if кк != 'хвост'} for ш, v in к.get('шаги', {}).items()}
    o['конвейер_стоп'] = к.get('стоп', '') or к.get('конец', '')
логи = sorted(glob.glob(os.path.join(DIR, '*%s*.log' % НАБОР)), key=os.path.getmtime)[-3:]
for л in логи:
    with open(л, encoding='utf-8', errors='replace') as f:
        o['лог ' + os.path.basename(л)] = f.read()[-700:]
try:
    r = subprocess.run(['powershell', '-NoProfile', '-Command',
                        "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and "
                        "($_.CommandLine -like '*pilot_*' -or $_.CommandLine -like '*kc_*' -or $_.CommandLine -like '*poisk_*') "
                        "-and $_.CommandLine -notlike '*_status_*' } | ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }"],
                       capture_output=True, text=True, timeout=60)
    o['процессы'] = [x[-90:] for x in r.stdout.splitlines() if x.strip()]
except Exception as e:  # noqa: BLE001
    o['процессы'] = repr(e)

# полоски для страницы хода: по каждому шагу — сделано / всего (из логов шагов и журналов набора)
import io, re  # noqa: E401,E402
ЭТАПЫ = [('poisk', 'Поиск (Яндекс, Google)', '—'), ('poisk_razbor.py', 'Разбор выдачи: сайт → ИНН/УНП', '—'),
         ('razbor_brauzer.py', 'Каталоги через браузер (checko, b2b.house)', '—'),
         ('pilot_otbor.py', 'Отбор: ОКВЭД → сегмент, сверка', 'Luna'), ('pilot_sayty_dobor.py', 'Сайты по названию', '—'),
         ('kc_kontakty.py', 'Обход сайтов: номера, почты, роли', 'Luna'), ('pilot_dop_proverka.py', 'Доп. ОКВЭД по сайту', 'Luna'),
         ('pilot_pasport.py', 'Паспорт сайта', 'GPT-5.6 Luna'), ('kc_audit.py', 'Чей номер / почта', 'Luna'),
         ('kc_audit2.py', 'Чей сайт по ИНН', '—'), ('kc_sayt_proverka.py', 'Проверка сайта', 'Sol'),
         ('kc_oproverzhenie.py', 'Опровергатели', 'Luna'), ('kc_glubokiy_vhod.py', 'Вход агентам', '—'),
         ('kc_agent_glubokiy.py', 'Агенты от 500 млн ₽', 'Sol'), ('kc_agent_glubokiy.py:хвост', 'Агенты 120–500 млн ₽', 'Luna'),
         ('kc_agent_pereproverka.py', 'Перепроверка агентов', 'Luna')]


def строк(х):
    ф = os.path.join(DIR, НАБОР + х)
    return sum(1 for _ in open(ф, encoding='utf-8', errors='replace')) if os.path.exists(ф) else 0


def лог_шага(шаг):
    файл, _, режим = шаг.partition(':')
    лл = sorted(glob.glob(os.path.join(DIR, 'konveyer_%s_%s_*.log' % (НАБОР, файл[:-3] + ('_' + режим if режим else '')))),
                key=os.path.getmtime)
    return io.open(лл[-1], encoding='utf-8', errors='replace').read() if лл else ''


def мин(с):
    try:
        return time.mktime(time.strptime(с, '%Y-%m-%d %H:%M')) / 60
    except (ValueError, TypeError):
        return None


import time  # noqa: E402
полосы = []
к = {}
ф = os.path.join(DIR, НАБОР + '-konveyer.json')
if os.path.exists(ф):
    к = json.load(open(ф, encoding='utf-8')).get('шаги', {})
по_файлу = {ключ.split(' ', 1)[-1]: v for ключ, v in к.items()}  # «N шаг» (по порядку) или «шаг» (волны)
кон = json.load(open(ф, encoding='utf-8')) if os.path.exists(ф) else {}
фон = кон.get('фон') or {}
лп = sorted(glob.glob(os.path.join(DIR, НАБОР + '_poisk_*.log')), key=os.path.getmtime)
for n, (шаг, имя, модель) in enumerate(ЭТАПЫ):
    р = {'n': n, 'этап': имя, 'модель': модель, 'сделано': None, 'всего': None, 'процент': 0, 'состояние': 'ждёт',
         'осталось_мин': None}
    if шаг == 'poisk':
        зд = json.load(open(r'C:\seostat\drop\drop-storage\%s-zadachi.json' % НАБОР, encoding='utf-8'))
        р['всего'] = sum(len(з['движки']) for з in зд)
        р['сделано'] = строк('-serp.jsonl')
        текст = io.open(лп[-1], encoding='utf-8', errors='replace').read() if лп else ''
        р['состояние'] = 'готово' if 'готово' in текст[-600:] else ('идёт' if лп else 'ждёт')
        if лп and р['состояние'] == 'идёт':
            прошло = (time.time() - os.path.getctime(лп[-1])) / 60
            if р['сделано']:
                р['осталось_мин'] = round(прошло * (р['всего'] - р['сделано']) / р['сделано'])
    elif шаг in по_файлу or (шаг == 'poisk_razbor.py' and лог_шага(шаг)):
        # разбор мог идти отдельным процессом (_pusk_meyer7t_razbor.py), а не шагом конвейера
        v = по_файлу.get(шаг) or {'конец': 'да' if 'готово' in лог_шага(шаг)[-200:] else '', 'код': 0,
                                  'старт': time.strftime('%Y-%m-%d %H:%M', time.localtime(max(
                                      os.path.getmtime(x) for x in glob.glob(os.path.join(DIR, 'konveyer_%s_poisk_razbor_*.log' % НАБОР))) - 60))}
        if фон.get(шаг) == 'идёт':
            v = dict(v, конец='')
        if v.get('конец') or (шаг in фон and фон[шаг] != 'идёт'):
            р['состояние'] = 'готово' if v.get('код', 0) == 0 and фон.get(шаг, 'код 0') == 'код 0' else 'ошибка'
        else:
            р['состояние'] = 'идёт'
            л = лог_шага(шаг)
            пары = re.findall(r'(\d+)/(\d+)', л)
            if пары:
                р['сделано'], р['всего'] = int(пары[-1][0]), int(пары[-1][1])
            elif шаг == 'poisk_razbor.py':
                м = re.findall(r'в очереди (\d+)(?: (\d+))?', л)
                д = re.findall(r'разобрано (\d+)', л)
                if м:
                    р['всего'], р['сделано'] = int(м[-1][0]) + int(м[-1][1] or 0), int(д[-1]) if д else 0
            elif шаг == 'pilot_sayty_dobor.py':
                м = re.findall(r'без сайта к поиску (\d+) уже в журнале (\d+)', л)
                if м:
                    р['всего'] = int(м[-1][0])
                    р['сделано'] = max(0, строк('-sayty-dobor.jsonl') - int(м[-1][1]))
            elif шаг == 'pilot_dop_proverka.py':
                м = re.findall(r'по доп\. ОКВЭД (\d+)', л)
                if м:
                    р['всего'], р['сделано'] = int(м[-1]), строк('-dop.jsonl')
            elif шаг == 'pilot_pasport.py':
                м = re.findall(r'компаний с открывшимся сайтом (\d+)', л)
                if м:
                    р['всего'], р['сделано'] = int(м[-1]), строк('-pasport.jsonl')
            с = мин(v.get('старт'))
            if р['сделано'] and р['всего'] and с:
                прошло = time.time() / 60 - с
                р['осталось_мин'] = round(max(0, прошло * (р['всего'] - р['сделано']) / р['сделано']))
    if р['состояние'] == 'готово':
        р['процент'] = 100
    elif р['сделано'] is not None and р['всего']:
        р['процент'] = min(99, round(100 * р['сделано'] / р['всего']))
    полосы.append(р)
o['полосы'] = полосы
try:
    оп = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    o['xmlriver'] = оп.open('http://xmlriver.com/api/get_balance/?user=%s&key=%s' % (
        os.environ.get('XMLRIVER_USER', ''), os.environ.get('XMLRIVER_KEY', '')), timeout=30).read(100).decode()
except Exception as e:  # noqa: BLE001
    o['xmlriver'] = repr(e)[:100]
o['время'] = time.strftime('%Y-%m-%d %H:%M:%S')
with io.open(r'C:\seostat\drop\drop-storage\%s-status.json' % НАБОР, 'w', encoding='utf-8') as f:
    json.dump(o, f, ensure_ascii=False, indent=1)
print('===ИТОГ===')
print(json.dumps({x: y for x, y in o.items() if x not in ('полосы', 'конвейер_сырой')}, ensure_ascii=False, indent=1))
print('полосы:', ' | '.join('%s %s%%' % (р['n'], р['процент']) for р in полосы if р['состояние'] != 'ждёт'))
