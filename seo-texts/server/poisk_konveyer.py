# -*- coding: utf-8 -*-
r"""Сбор с нуля поиском (владелец 07.10, «к утру Excel»): ночной конвейер агентов на сервере.

Ждёт окончания поиска (poisk_zaprosy.py, свой процесс) -> разбор выдачи -> отбор (доход, ОКВЭД,
сегмент, запреты, сайт) -> обход сайтов + закупки + описание (kc_kontakty, набор poisk) ->
«чей сайт» и «чей номер» (kc_audit, kc_audit2). Каждый шаг — отдельный процесс с резюмом.
Статус: C:\sender\server\poisk-konveyer.json (+ дроп). Запуск детачем: _pusk_poisk_konveyer.py.
"""
import glob
import io
import json
import os
import shutil
import subprocess
import sys
import time

DIR = r'C:\sender\server'
ДРОП = r'C:\seostat\drop\drop-storage'
СТАТУС = os.path.join(DIR, 'poisk-konveyer.json')
# два прохода: 1-й — без DaData (лимит суток выбран), 2-й — после полуночи МСК, с DaData (резюм)
ПРОХОД1 = {'POISK_NE_ZHDAT': '1', 'POISK_CHECKO_MINUT': '100'}
# 08.10 04:55: ночью отбор упал (на сервере не было meyer_baza.py) — после полуночи DaData свежая, один полный проход
ШАГИ = [('poisk_razbor.py', {}, ''), ('poisk_otbor.py', {}, ''), ('kc_kontakty.py', {}, ''),
        ('kc_audit.py', {}, ''), ('kc_audit2.py', {}, '')]


def занят(скрипт):
    """Шаг уже идёт отдельным процессом (остался от прошлого запуска конвейера) — ждать его."""
    cmd = ("@(Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and "
           "$_.CommandLine -like '*%s*' }).Count" % скрипт)
    r = subprocess.run(['powershell', '-NoProfile', '-Command', cmd], capture_output=True, text=True, timeout=120)
    try:
        return int((r.stdout or '0').strip() or 0) > 0
    except ValueError:
        return False


def статус(o):
    with io.open(СТАТУС, 'w', encoding='utf-8') as f:
        json.dump(o, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    shutil.copyfile(СТАТУС, os.path.join(ДРОП, 'poisk-konveyer.json'))


def поиск_закончен():
    логи = sorted(glob.glob(os.path.join(DIR, 'poisk_zaprosy_*.log')), key=os.path.getmtime)
    return bool(логи) and 'готово' in io.open(логи[-1], encoding='utf-8', errors='replace').read()[-400:]


def main():
    o = {'начало': time.strftime('%Y-%m-%d %H:%M'), 'шаги': {}}
    статус(o)
    while not поиск_закончен():
        o['ожидание'] = 'жду окончания поиска, %s' % time.strftime('%H:%M')
        статус(o)
        time.sleep(120)
    o.pop('ожидание', None)
    for n, (шаг, доп, условие) in enumerate(ШАГИ):
        env = dict(os.environ, KC_NABOR='poisk', **доп)
        ключ = '%d %s%s' % (n + 1, шаг, ' (1-й проход)' if доп.get('POISK_NE_ZHDAT') else '')
        if условие == 'после полуночи':
            день = o['начало'][:10]
            while time.strftime('%Y-%m-%d') == день or time.strftime('%H:%M') < '00:10':
                o['ожидание'] = 'жду обнуления лимита DaData (00:10 МСК), %s' % time.strftime('%H:%M')
                статус(o)
                time.sleep(300)
            o.pop('ожидание', None)
        while занят(шаг):
            o['ожидание'] = '%s уже идёт отдельным процессом — жду, %s' % (шаг, time.strftime('%H:%M'))
            статус(o)
            time.sleep(60)
        o.pop('ожидание', None)
        o['шаги'][ключ] = {'старт': time.strftime('%Y-%m-%d %H:%M')}
        статус(o)
        лог = os.path.join(DIR, 'konveyer_poisk_%s_%s.log' % (шаг[:-3], time.strftime('%d%m-%H%M')))
        for попытка in range(2):  # упал — один перезапуск (резюм внутри шагов)
            with open(лог, 'ab') as f:
                r = subprocess.run([sys.executable, '-u', os.path.join(DIR, шаг)], cwd=DIR, env=env,
                                   stdout=f, stderr=subprocess.STDOUT)
            if r.returncode == 0:
                break
        o['шаги'][ключ].update({'конец': time.strftime('%Y-%m-%d %H:%M'), 'код': r.returncode,
                               'хвост': io.open(лог, encoding='utf-8', errors='replace').read()[-500:]})
        статус(o)
        if n == 4 and len(ШАГИ) > 5:  # конец 1-го прохода — копии на дроп для промежуточного Excel
            for ф in ('poisk-spisok.json', 'poisk-kontakty.jsonl', 'poisk-audit.jsonl', 'poisk-audit2.jsonl'):
                if os.path.exists(os.path.join(DIR, ф)):
                    shutil.copyfile(os.path.join(DIR, ф), os.path.join(ДРОП, ф))
            o['проход1_готов'] = time.strftime('%Y-%m-%d %H:%M')
            статус(o)
    for ф in ('poisk-serp.jsonl', 'poisk-razbor.jsonl', 'poisk-spisok.json', 'poisk-okved.jsonl',
              'poisk-kontakty.jsonl', 'poisk-audit.jsonl', 'poisk-audit2.jsonl'):
        if os.path.exists(os.path.join(DIR, ф)):
            shutil.copyfile(os.path.join(DIR, ф), os.path.join(ДРОП, ф))
    o['конец'] = time.strftime('%Y-%m-%d %H:%M')
    статус(o)


if __name__ == '__main__':
    main()
