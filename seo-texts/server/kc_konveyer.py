# -*- coding: utf-8 -*-
r"""База КЦ от 1,5 млрд (владелец 07.10): конвейер на сервере, чтобы шёл без сессии.
ОКВЭД по ФНС-юрлицам (checko сразу, DaData после полуночи) -> список -> контакты -> поиск сайтов.
Каждый шаг — отдельный процесс с резюмом; статус — C:\sender\server\kc-konveyer.json (+ дроп).
Запуск детачем: _pusk_kc_konveyer.py.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import time

DIR = r'C:\sender\server'
ДРОП = r'C:\seostat\drop\drop-storage'
СТАТУС = os.path.join(DIR, 'kc-konveyer.json')
ШАГИ = ['kc_okved_fns.py', 'kc_spisok.py', 'kc_kontakty.py', 'kc_sayty.py']


def статус(o):
    with io.open(СТАТУС, 'w', encoding='utf-8') as f:
        json.dump(o, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    shutil.copyfile(СТАТУС, os.path.join(ДРОП, 'kc-konveyer.json'))


def main():
    o = {'начало': time.strftime('%Y-%m-%d %H:%M'), 'шаги': {}}
    for шаг in ШАГИ:
        o['шаги'][шаг] = {'старт': time.strftime('%Y-%m-%d %H:%M')}
        статус(o)
        лог = os.path.join(DIR, 'konveyer_%s_%s.log' % (шаг[:-3], time.strftime('%d%m-%H%M')))
        with open(лог, 'wb') as f:
            r = subprocess.run([sys.executable, '-u', os.path.join(DIR, шаг)], cwd=DIR, stdout=f, stderr=subprocess.STDOUT)
        o['шаги'][шаг].update({'конец': time.strftime('%Y-%m-%d %H:%M'), 'код': r.returncode,
                               'хвост': io.open(лог, encoding='utf-8', errors='replace').read()[-400:]})
        статус(o)
    for ф in ('kc-spisok.json', 'kc-kontakty.jsonl', 'kc-sayty.jsonl', 'kc-okved-fns.jsonl'):
        if os.path.exists(os.path.join(DIR, ф)):
            shutil.copyfile(os.path.join(DIR, ф), os.path.join(ДРОП, ф))
    o['конец'] = time.strftime('%Y-%m-%d %H:%M')
    статус(o)


if __name__ == '__main__':
    main()
