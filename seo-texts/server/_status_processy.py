# -*- coding: utf-8 -*-
r"""Состояние всех активных процессов сессии для страницы хода (владелец 09.10: «интерактив с прогрессом каждого
активного процесса, чтобы понимал, что идёт»). Строки: процесс, этап, сделано/всего, состояние, осталось, пояснение.
Источники: статусы оркестраторов (<набор>-dovodka*.json), логи шагов («готово N/M», «фаза A готово n/m»), журналы
сравнения, очередь Зенки, живые python-процессы шагов. -> processy-status.json на дроп + ===ИТОГ===."""
import glob
import io
import json
import os
import re
import subprocess
import time

DIR = r'C:\sender\server'
ДРОП = r'C:\seostat\drop\drop-storage'
ZENNO = r'C:\seostat\drop\zenno'
НАБОР = 'meyer7t'
строки = []


def лог(шаблон):
    лл = sorted(glob.glob(os.path.join(DIR, шаблон)), key=os.path.getmtime)
    return (io.open(лл[-1], encoding='utf-8', errors='replace').read(), лл[-1]) if лл else ('', '')


def мин_с(hhmm):
    """Минут прошло с ЧЧ:ММ (серверное время, сегодня)."""
    try:
        ч, м = map(int, hhmm[-5:].split(':'))
        t = time.localtime()
        return max(0, (t.tm_hour * 60 + t.tm_min) - (ч * 60 + м)) % 1440
    except (ValueError, AttributeError):
        return None


def строка(процесс, этап, сделано=None, всего=None, состояние='ждёт', прошло=None, пояснение=''):
    п = 100 if состояние == 'готово' else (min(99, round(100 * сделано / всего)) if сделано is not None and всего else 0)
    ост = round(прошло * (всего - сделано) / сделано) if состояние == 'идёт' and прошло and сделано and всего else None
    строки.append({'ключ': '%02d' % len(строки), 'процесс': процесс, 'этап': этап, 'сделано': сделано, 'всего': всего,
                   'процент': п, 'состояние': состояние, 'осталось_мин': ост, 'пояснение': пояснение[:160]})


# живые python-процессы (для «идёт» без статуса)
try:
    r = subprocess.run(['powershell', '-NoProfile', '-Command',
                        "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' } | "
                        "ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }"], capture_output=True, text=True, timeout=120)
    живые = r.stdout
except Exception:  # noqa: BLE001
    живые = ''

# 0) полный прогон (набор meyer7): полоски шагов — из статус-скрипта набора (_status_meyer7.py пишет meyer7-status.json)
if os.path.exists(os.path.join(DIR, 'meyer7-serp.jsonl')) or os.path.exists(os.path.join(DIR, 'meyer7-konveyer.json')):
    import contextlib
    import runpy
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(os.path.join(DIR, '_status_meyer7.py'), run_name='__main__')
        ст7 = json.load(io.open(os.path.join(ДРОП, 'meyer7-status.json'), encoding='utf-8'))
        кон7 = ст7.get('конвейер_ждёт') or ''
        for р in ст7.get('полосы', []):
            if р['состояние'] == 'ждёт' and not р.get('сделано'):
                строка('Полный прогон (meyer7)', р['этап'] + (' · ' + р['модель'] if р['модель'] not in ('—', '') else ''),
                       пояснение=р.get('пояснение') or '')
                continue
            строки.append({'ключ': '%02d' % len(строки), 'процесс': 'Полный прогон (meyer7)',
                           'этап': р['этап'] + (' · ' + р['модель'] if р['модель'] not in ('—', '') else ''),
                           'сделано': р['сделано'], 'всего': р['всего'], 'процент': р['процент'], 'состояние': р['состояние'],
                           'осталось_мин': р['осталось_мин'], 'пояснение': '; '.join(x for x in (
                               ('волна %s' % ст7.get('волна')) if ст7.get('волна') else кон7, р.get('пояснение') or '') if x)})
    except Exception as e:  # noqa: BLE001
        строка('Полный прогон (meyer7)', 'статус не собран', состояние='ошибка', пояснение=repr(e)[:150])

# 1) перепрогон обхода по 110 (dovodka4)
ИМЕНА = {'kc_kontakty.py': 'Обход сайтов: номера, почты, роли', 'kc_audit.py': 'Чей номер / почта', 'kc_audit2.py': 'Чей сайт по ИНН',
         'kc_sayt_proverka.py': 'Проверка сайта (Sol)', 'kc_oproverzhenie.py': 'Опровергатели'}
for метка, назв in (('dovodka4', 'Перепрогон 110 (v2: кэш + извлекатели сервера)'), ('dovodka5', 'Перепрогон 110 (v3: + серверный обогатитель)')):
    п = os.path.join(DIR, '%s-%s.json' % (НАБОР, метка))
    if not os.path.exists(п):
        continue
    o = json.load(io.open(п, encoding='utf-8'))
    for шаг, имя in ИМЕНА.items():
        v = o.get('шаги', {}).get(шаг)
        if not v:
            строка(назв, имя)
            continue
        if v.get('конец'):
            строка(назв, имя, состояние='готово' if v.get('код') == 0 else 'ошибка',
                   пояснение='%s–%s' % (v.get('старт'), v.get('конец')) + ('' if v.get('код') == 0 else ' код %s' % v.get('код')))
            continue
        т, _ = лог('konveyer_%s_%s_%s_*.log' % (НАБОР, шаг[:-3], метка[-1]))
        пары = re.findall(r'готово (\d+)/(\d+)', т) or re.findall(r'(\d+)/(\d+)', т)
        м = re.findall(r'в очереди (\d+)', т)
        с, в = (int(пары[-1][0]), int(пары[-1][1])) if пары else (0, int(м[-1]) if м else None)
        if шаг == 'kc_kontakty.py' and o.get('версия'):  # лог пишет раз в 20 компаний — точнее по записям версии
            с = sum(1 for x in io.open(os.path.join(DIR, НАБОР + '-kontakty.jsonl'), encoding='utf-8', errors='replace')
                    if '"версия": "%s"' % o['версия'] in x)
        строка(назв, имя, с, в, 'идёт', мин_с(v.get('старт')), 'с %s' % v.get('старт'))

# 2) сравнение с серверным обогатителем на новых сайтах
т, путь = лог('konveyer_%s_sravnenie_ec_*.log' % НАБОР)
выход = os.path.join(DIR, НАБОР + '-sravnenie-ec.jsonl')
if т or os.path.exists(выход):
    фазы = {}
    if os.path.exists(выход):
        for s in io.open(выход, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
                фазы[з['фаза']] = фазы.get(з['фаза'], 0) + 1
            except (ValueError, KeyError):
                pass
    всего = re.findall(r'фаза (\w) компаний (\d+)', т)
    жив = 'kc_sravnenie_ec' in живые
    старт = time.strftime('%H:%M', time.localtime(os.path.getctime(путь))) if путь else ''
    for ф, имя in (('A', 'A: серверный обогатитель как есть'), ('B', 'B: наш обход'),
                   ('C', 'C: наш обход, обогатитель без своей модели')):
        if ф == 'C' and not фазы.get('C') and 'sravnenie_ec_C' not in живые:
            continue
        в = [int(n) for x, n in всего if x == ф]
        сд = фазы.get(ф, 0)
        n_все = int(os.environ.get('KC_SRAV_N', '30'))
        жив_ф = ('sravnenie_ec_C' in живые) if ф == 'C' else жив
        сост = 'готово' if сд >= n_все else ('идёт' if жив_ф and (ф != 'B' or фазы.get('A', 0) >= n_все or в) else 'ждёт')
        строка('Сравнение на новых сайтах (30 компаний без кэша)', имя, сд, n_все, сост, None, 'журнал: %d компаний' % сд)

# 3) очередь Зенки (наша)
п = os.path.join(ZENNO, НАБОР + '-ochered-gotova.txt')
if os.path.exists(п):
    наши = [x.split(';')[0] for x in io.open(п, encoding='utf-8', errors='replace') if ';' in x]
    живая = io.open(os.path.join(ZENNO, 'ochered.txt'), encoding='utf-8', errors='replace').read() if os.path.exists(os.path.join(ZENNO, 'ochered.txt')) else ''
    в_очереди = sum(1 for i in наши if i + ';' in живая)
    готово = sum(1 for i in наши if glob.glob(os.path.join(ZENNO, 'gotovo', i + '*')) or glob.glob(os.path.join(ZENNO, 'razobrano', i + '*')))
    строка('Зенка: сайты, которые не открылись', 'обход браузером Зенки', готово, len(наши) or None,
           'готово' if наши and готово >= len(наши) else ('идёт' if в_очереди or готово else 'ждёт'),
           пояснение='в живой очереди %d, готово %d из %d' % (в_очереди, готово, len(наши)))

# 4) прочие живые шаги
for x in живые.splitlines():
    if re.search(r'server\\(kc_|pilot_|poisk_|_dovodka|kc_sravnenie)', x) and not any(
            k in x for k in ('dovodka4', 'dovodka5', 'kc_sravnenie_ec', '_status_')) and not re.search(r'--shag=\S+_[45]\b', x):
        м = re.search(r'server\\(\S+\.py)', x)
        if м and not any(р['этап'] == м.group(1) for р in строки):
            строка('Прочие процессы', м.group(1), состояние='идёт', пояснение=x[-90:])

# 5) агенты (kc_agent_glubokiy) — если идут
for x in живые.splitlines():
    if 'kc_agent_glubokiy' in x or 'kc_agent_pereproverka' in x:
        т, _ = лог('konveyer_*kc_agent_*.log')
        пары = re.findall(r'(\d+)/(\d+)', т)
        строка('Агенты-исследователи', re.search(r'(kc_agent_\w+)', x).group(1), int(пары[-1][0]) if пары else None,
               int(пары[-1][1]) if пары else None, 'идёт', пояснение=x[-80:])
# 6) xmlriver — баланс (траты считает сессия по разнице с началом доработки)
try:
    import urllib.request
    оп = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    баланс = оп.open('http://xmlriver.com/api/get_balance/?user=%s&key=%s' % (
        os.environ.get('XMLRIVER_USER', ''), os.environ.get('XMLRIVER_KEY', '')), timeout=30).read(100).decode().strip()
except Exception as e:  # noqa: BLE001
    баланс = 'ошибка ' + repr(e)[:60]
for р in строки:
    р['обновлено'] = time.strftime('%d.%m %H:%M')
o = {'rows': строки, 'обновлено': time.strftime('%Y-%m-%d %H:%M:%S'), 'xmlriver': баланс}
with io.open(os.path.join(ДРОП, 'processy-status.json'), 'w', encoding='utf-8') as f:
    json.dump(o, f, ensure_ascii=False, indent=0)
print('===ИТОГ===')
print('xmlriver', баланс)
for р in строки:
    print('%s | %s | %s/%s %s%% %s ост %s | %s' % (р['процесс'][:30], р['этап'][:34], р['сделано'], р['всего'], р['процент'],
                                                  р['состояние'], р['осталось_мин'], р['пояснение'][:60]))
