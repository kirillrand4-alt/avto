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
НАБОР = os.environ.get('POISK_NABOR', 'pilot')  # для полного прогона — свой набор (meyer7 и т.п.)
СТАТУС = os.path.join(DIR, НАБОР + '-konveyer.json')
# 09.10: + сайты по названию для компаний из каталогов (после отбора) и проверка доп. ОКВЭД по сайту (после обхода)
ВСЕ_ШАГИ = ['poisk_razbor.py', 'pilot_otbor.py', 'pilot_sayty_dobor.py', 'kc_kontakty.py', 'pilot_dop_proverka.py',
            'pilot_pasport.py', 'kc_audit.py', 'kc_audit2.py', 'kc_sayt_proverka.py', 'kc_oproverzhenie.py', 'kc_glubokiy_vhod.py',
            'kc_agent_glubokiy.py', 'kc_agent_glubokiy.py:хвост', 'kc_agent_pereproverka.py']
С_ШАГА = int(os.environ.get('PILOT_S_SHAGA', '0'))
# модель по шагам (сравнение моделей 09.10, решение владельца «согласен»): GPT-6 Luna — классификация (94% совпадения с
# эталоном при $0,0002 за вызов), GPT-6 Sol — проверка сайта (лучшая, 96%) и агенты-исследователи (многошаговые)
# агенты (сравнение Luna/Sol 09.10 на 100 одинаковых компаниях): Sol находит ~в 1,5 раза больше номеров ЛПР и лучше на
# выручке 0,6–2 млрд; ниже ~120 млн ₽ обе модели не находят почти ничего. Поэтому: агенты — только от KC_AGENT_OT
# (120 млн), все на Sol (~$0,08 на компанию). Хвост (AGENT_HVOST_MODEL) по умолчанию выключен («нет»): включить —
# gpt-6-luna, тогда он пройдёт оставшихся (сделанных агент пропускает сам), KC_AGENT_OT для хвоста снимается
МОДЕЛЬ_ШАГА = {'kc_sayt_proverka.py': 'gpt-6-sol', 'kc_agent_glubokiy.py': 'gpt-6-sol',
               'kc_agent_glubokiy.py:хвост': os.environ.get('AGENT_HVOST_MODEL', 'нет')}
МОДЕЛЬ_ОСН = os.environ.get('PILOT_MODEL', 'gpt-6-luna')
ШАГИ = ВСЕ_ШАГИ[С_ШАГА:]


def статус(o):
    with io.open(СТАТУС, 'w', encoding='utf-8') as f:
        json.dump(o, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    shutil.copyfile(СТАТУС, os.path.join(ДРОП, НАБОР + '-konveyer.json'))


def поиск_готов():
    логи = sorted(glob.glob(os.path.join(DIR, НАБОР + '_poisk_*.log')), key=os.path.getmtime)
    if not логи:
        return True
    return 'готово' in io.open(логи[-1], encoding='utf-8', errors='replace').read()[-600:]


def разбор_жив():
    """Ранний разбор (_pusk_*_razbor.py) ещё идёт? Два разбора в один файл писать не должны."""
    r = subprocess.run(['powershell', '-NoProfile', '-Command',
                        "(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*server\\poisk_razbor.py*' }).Count"],
                       capture_output=True, text=True, timeout=120)
    return (r.stdout.strip() or '0') not in ('0', '')


def main():
    o = {'начало': time.strftime('%Y-%m-%d %H:%M'), 'шаги': {}}
    while not поиск_готов():
        o['ждём'] = 'поиск ещё идёт ' + time.strftime('%H:%M')
        статус(o)
        time.sleep(60)
    while разбор_жив():
        o['ждём'] = 'ранний разбор ещё идёт ' + time.strftime('%H:%M')
        статус(o)
        time.sleep(60)
    o.pop('ждём', None)
    env = dict(os.environ, KC_NABOR=НАБОР, POISK_NABOR=НАБОР, KC_CEL='meyer', POISK_NE_ZHDAT='1',
               POISK_CHECKO_MINUT='40', KC_AGENT_OT=os.environ.get('KC_AGENT_OT', '120e6'),
               KC_BEZ_CHECKO='1', KC_ZAKUPKI_OT=os.environ.get('KC_ZAKUPKI_OT', '1e9'),
               KC_POTOKOV_SHAGA=os.environ.get('KC_POTOKOV_SHAGA', '24'), KC_AGENT_POTOKOV=os.environ.get('KC_AGENT_POTOKOV', '30'),
               PASPORT_POTOKOV=os.environ.get('PASPORT_POTOKOV', '24'),
               KC_POTOKOV=os.environ.get('KC_POTOKOV', '24'))  # обход: без этого у не-pilot наборов 6 потоков
    for n, шаг in enumerate(ШАГИ):
        ключ = '%d %s' % (n + 1 + С_ШАГА, шаг)
        модель = МОДЕЛЬ_ШАГА.get(шаг, МОДЕЛЬ_ОСН)
        if модель == 'нет':
            continue
        файл, _, режим = шаг.partition(':')
        env_шага = dict(env, PROVIDER_MODEL=модель)
        if режим == 'хвост':
            env_шага.pop('KC_AGENT_OT', None)  # все оставшиеся
        o['шаги'][ключ] = {'старт': time.strftime('%Y-%m-%d %H:%M'), 'модель': модель}
        статус(o)
        лог = os.path.join(DIR, 'konveyer_%s_%s_%s.log' % (НАБОР, файл[:-3] + ('_' + режим if режим else ''),
                                                           time.strftime('%d%m-%H%M')))
        for попытка in range(2):
            with open(лог, 'ab') as f:
                r = subprocess.run([sys.executable, '-u', os.path.join(DIR, файл)], cwd=DIR, env=env_шага,
                                   stdout=f, stderr=subprocess.STDOUT)
            if r.returncode == 0:
                break
        o['шаги'][ключ].update({'конец': time.strftime('%Y-%m-%d %H:%M'), 'код': r.returncode,
                               'хвост': io.open(лог, encoding='utf-8', errors='replace').read()[-500:]})
        статус(o)
        if r.returncode != 0 and шаг in ('poisk_razbor.py', 'pilot_otbor.py', 'pilot_sayty_dobor.py', 'kc_kontakty.py'):
            o['стоп'] = 'шаг %s упал — дальше без него нельзя' % шаг
            статус(o)
            return
    for ф in (НАБОР + x for x in ('-razbor.jsonl', '-spisok.json', '-reestr.json', '-zenka.json', '-kontakty.jsonl',
                                   '-audit.jsonl', '-audit2.jsonl', '-sayt-proverka.jsonl', '-oprov.jsonl', '-glubokiy.jsonl',
                                   '-glubokiy2.jsonl', '-serp.jsonl', '-dop.jsonl', '-sayty-dobor.jsonl', '-klass.jsonl',
                                   '-pasport.jsonl')):
        if os.path.exists(os.path.join(DIR, ф)):
            shutil.copyfile(os.path.join(DIR, ф), os.path.join(ДРОП, ф))
    o['конец'] = time.strftime('%Y-%m-%d %H:%M')
    статус(o)


if __name__ == '__main__':
    main()
