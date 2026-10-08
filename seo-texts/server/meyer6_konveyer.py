# -*- coding: utf-8 -*-
r"""Файл 6 Meyer (владелец 08.10): компании из сбора поиском (выше и ниже 1,5 млрд) — выручка от 30 млн или
неизвестна, без напитков; повторы с файлами 1–5 помечаются при сборке. Тот же конвейер, что у базы КЦ, набор meyer6, ЛПР — по Meyer.
Статус: C:\sender\server\meyer6-konveyer.json (+ дроп). Запуск детачем: _pusk_meyer6.py.
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
СТАТУС = os.path.join(DIR, 'meyer6-konveyer.json')
ВСЕ_ШАГИ = ['kc_meyer6_spisok.py', 'kc_kontakty.py', 'kc_audit.py', 'kc_audit2.py', 'kc_sayt_proverka.py', 'kc_glubokiy_vhod.py',
            'kc_agent_glubokiy.py', 'kc_agent_pereproverka.py']
# 08.10 10:40 кончился баланс провайдера на шаге проверки сайтов — продолжаем с него (шаги 1–4 готовы)
ШАГИ = ВСЕ_ШАГИ[4:]


def статус(o):
    with io.open(СТАТУС, 'w', encoding='utf-8') as f:
        json.dump(o, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    shutil.copyfile(СТАТУС, os.path.join(ДРОП, 'meyer6-konveyer.json'))


def main():
    o = {'начало': time.strftime('%Y-%m-%d %H:%M'), 'шаги': {}}
    env = dict(os.environ, KC_NABOR='meyer6', KC_CEL='meyer')
    for n, шаг in enumerate(ШАГИ):
        ключ = '%d %s' % (n + 1, шаг)
        o['шаги'][ключ] = {'старт': time.strftime('%Y-%m-%d %H:%M')}
        статус(o)
        лог = os.path.join(DIR, 'konveyer_meyer6_%s_%s.log' % (шаг[:-3], time.strftime('%d%m-%H%M')))
        for попытка in range(2):
            with open(лог, 'ab') as f:
                r = subprocess.run([sys.executable, '-u', os.path.join(DIR, шаг)], cwd=DIR, env=env,
                                   stdout=f, stderr=subprocess.STDOUT)
            if r.returncode == 0:
                break
        o['шаги'][ключ].update({'конец': time.strftime('%Y-%m-%d %H:%M'), 'код': r.returncode,
                               'хвост': io.open(лог, encoding='utf-8', errors='replace').read()[-400:]})
        статус(o)
    for ф in ('meyer6-kontakty.jsonl', 'meyer6-audit.jsonl', 'meyer6-audit2.jsonl', 'meyer6-sayt-proverka.jsonl',
              'meyer6-glubokiy2.jsonl'):
        if os.path.exists(os.path.join(DIR, ф)):
            shutil.copyfile(os.path.join(DIR, ф), os.path.join(ДРОП, ф))
    o['конец'] = time.strftime('%Y-%m-%d %H:%M')
    статус(o)


if __name__ == '__main__':
    main()
