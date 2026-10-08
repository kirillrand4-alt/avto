# -*- coding: utf-8 -*-
r"""Пилот плана Meyer (владелец 08.10): конвейер после поиска. Ждёт окончания pilot_poisk.py (строка «готово»
в последнем логе pilot_poisk_*.log), затем шаги плана в наборе pilot (KC_NABOR=pilot, POISK_NABOR=pilot):
разбор -> отбор + обратная сверка -> обход (номера + почты + роли) -> чей номер -> чей сайт -> модель о сайте ->
ОПРОВЕРГАТЕЛИ -> вход агентам (без сайта + опровергнутые) -> агенты (лимит по балансу xmlriver) -> перепроверка.
Статус: C:\sender\server\pilot-konveyer.json (+ дроп). Запуск детачем: _pusk_pilot_konveyer.py.
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
СТАТУС = os.path.join(DIR, 'pilot-konveyer.json')
ВСЕ_ШАГИ = ['poisk_razbor.py', 'pilot_otbor.py', 'kc_kontakty.py', 'kc_audit.py', 'kc_audit2.py', 'kc_sayt_proverka.py',
            'kc_oproverzhenie.py', 'kc_glubokiy_vhod.py', 'kc_agent_glubokiy.py', 'kc_agent_pereproverka.py']
С_ШАГА = int(os.environ.get('PILOT_S_SHAGA', '0'))
ШАГИ = ВСЕ_ШАГИ[С_ШАГА:]


def статус(o):
    with io.open(СТАТУС, 'w', encoding='utf-8') as f:
        json.dump(o, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    shutil.copyfile(СТАТУС, os.path.join(ДРОП, 'pilot-konveyer.json'))


def поиск_готов():
    логи = sorted(glob.glob(os.path.join(DIR, 'pilot_poisk_*.log')), key=os.path.getmtime)
    if not логи:
        return True
    return 'готово' in io.open(логи[-1], encoding='utf-8', errors='replace').read()[-600:]


def main():
    o = {'начало': time.strftime('%Y-%m-%d %H:%M'), 'шаги': {}}
    while not поиск_готов():
        o['ждём'] = 'поиск ещё идёт ' + time.strftime('%H:%M')
        статус(o)
        time.sleep(60)
    o.pop('ждём', None)
    env = dict(os.environ, KC_NABOR='pilot', POISK_NABOR='pilot', KC_CEL='meyer', POISK_NE_ZHDAT='1',
               POISK_CHECKO_MINUT='40', KC_AGENT_LIMIT=os.environ.get('KC_AGENT_LIMIT', '60'))
    for n, шаг in enumerate(ШАГИ):
        ключ = '%d %s' % (n + 1 + С_ШАГА, шаг)
        o['шаги'][ключ] = {'старт': time.strftime('%Y-%m-%d %H:%M')}
        статус(o)
        лог = os.path.join(DIR, 'konveyer_pilot_%s_%s.log' % (шаг[:-3], time.strftime('%d%m-%H%M')))
        for попытка in range(2):
            with open(лог, 'ab') as f:
                r = subprocess.run([sys.executable, '-u', os.path.join(DIR, шаг)], cwd=DIR, env=env,
                                   stdout=f, stderr=subprocess.STDOUT)
            if r.returncode == 0:
                break
        o['шаги'][ключ].update({'конец': time.strftime('%Y-%m-%d %H:%M'), 'код': r.returncode,
                               'хвост': io.open(лог, encoding='utf-8', errors='replace').read()[-500:]})
        статус(o)
        if r.returncode != 0 and шаг in ('poisk_razbor.py', 'pilot_otbor.py', 'kc_kontakty.py'):
            o['стоп'] = 'шаг %s упал — дальше без него нельзя' % шаг
            статус(o)
            return
    for ф in ('pilot-razbor.jsonl', 'pilot-spisok.json', 'pilot-reestr.json', 'pilot-kontakty.jsonl', 'pilot-audit.jsonl',
              'pilot-audit2.jsonl', 'pilot-sayt-proverka.jsonl', 'pilot-oprov.jsonl', 'pilot-glubokiy.jsonl',
              'pilot-glubokiy2.jsonl', 'pilot-serp.jsonl'):
        if os.path.exists(os.path.join(DIR, ф)):
            shutil.copyfile(os.path.join(DIR, ф), os.path.join(ДРОП, ф))
    o['конец'] = time.strftime('%Y-%m-%d %H:%M')
    статус(o)


if __name__ == '__main__':
    main()
