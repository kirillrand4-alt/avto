# -*- coding: utf-8 -*-
r"""Доводка пробы meyer7t после обхода (владелец 09.10: «как ускорить время теста?»). Вместо оркестратора по порядку:
ждёт конца обхода (kc_kontakty.py идёт отдельным процессом), затем
  * доп. ОКВЭД и паспорт — фоном (от них дальше ничего не зависит, нужны только Excel);
  * чей номер -> чей сайт -> проверка сайта Sol -> опровергатели -> вход агентам — по порядку;
  * агенты Sol (от 500 млн) и Luna (120–500 млн, KC_AGENT_DO, свой файл) — одновременно, по 40 потоков, лимит 40;
  * слияние журнала Luna в общий, ожидание фоновых, перепроверка агентов, копии на дроп.
Статус — в meyer7t-konveyer.json (шаги прежнего оркестратора сохраняются).
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
НАБОР = 'meyer7t'
СТАТУС = os.path.join(DIR, НАБОР + '-konveyer.json')
ЛУНА = 'glubokiy-hvost.jsonl'
МОДЕЛЬ = {'kc_sayt_proverka.py': 'gpt-6-sol', 'kc_agent_glubokiy.py': 'gpt-6-sol', 'kc_agent_glubokiy.py:хвост': 'gpt-6-luna'}
НОМЕР = {'pilot_dop_proverka.py': 5, 'pilot_pasport.py': 6, 'kc_audit.py': 7, 'kc_audit2.py': 8, 'kc_sayt_proverka.py': 9,
         'kc_oproverzhenie.py': 10, 'kc_glubokiy_vhod.py': 11, 'kc_agent_glubokiy.py': 12, 'kc_agent_glubokiy.py:хвост': 13,
         'kc_agent_pereproverka.py': 14}
ENV = dict(os.environ, KC_NABOR=НАБОР, POISK_NABOR=НАБОР, KC_CEL='meyer', POISK_NE_ZHDAT='1', POISK_CHECKO_MINUT='40',
           KC_AGENT_OT='500e6', KC_BEZ_CHECKO='1', KC_ZAKUPKI_OT='1e9', KC_POTOKOV_SHAGA='24', KC_AGENT_POTOKOV='40',
           PASPORT_POTOKOV='24', KC_POTOKOV='24', PROVIDER_FALLBACK_CHEAP='gpt-6-luna', KC_AGENT_LIMIT='40',
           POISK_REGIONY_SVERKI='все')

o = json.load(io.open(СТАТУС, encoding='utf-8')) if os.path.exists(СТАТУС) else {'шаги': {}}
o.pop('конец', None)
o['доводка'] = time.strftime('%Y-%m-%d %H:%M')
фон = {}


def статус():
    o['фон'] = {ш: ('идёт' if п.poll() is None else 'код %s' % п.returncode) for ш, п in фон.items()}
    for ш, п in фон.items():
        к = '%d %s' % (НОМЕР[ш], ш)
        if п.poll() is not None and not o['шаги'][к].get('конец'):
            o['шаги'][к].update({'конец': time.strftime('%Y-%m-%d %H:%M'), 'код': п.returncode})
    with io.open(СТАТУС, 'w', encoding='utf-8') as f:
        json.dump(o, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    shutil.copyfile(СТАТУС, os.path.join(ДРОП, НАБОР + '-konveyer.json'))


def идёт(шаблон):
    # 09.10: «(...).Count» из Python возвращал пусто при живом процессе — перечисляем PID
    r = subprocess.run(['powershell', '-NoProfile', '-Command',
                        "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and "
                        "$_.CommandLine -like '%s' } | ForEach-Object { $_.ProcessId }" % шаблон],
                       capture_output=True, text=True, timeout=120)
    return bool(r.stdout.split())


ПИТОН_ПАНЕЛИ = r'C:\Program Files\Python311\python.exe'  # 09.10: anthropic (site_facts -> gen_provider) есть только в нём


def env_шага(шаг):
    e = dict(ENV, PROVIDER_MODEL=МОДЕЛЬ.get(шаг, 'gpt-6-luna'))
    if шаг.endswith(':хвост'):
        e.update(KC_AGENT_OT='120e6', KC_AGENT_DO='500e6', KC_AGENT_FAYL=ЛУНА)
    return e


def пуск(шаг, фоном=False):
    файл, _, режим = шаг.partition(':')
    к = '%d %s' % (НОМЕР[шаг], шаг)
    o['шаги'][к] = {'старт': time.strftime('%Y-%m-%d %H:%M'), 'модель': МОДЕЛЬ.get(шаг, 'gpt-6-luna'), 'фоном': фоном}
    статус()
    лог = os.path.join(DIR, 'konveyer_%s_%s_%s.log' % (НАБОР, файл[:-3] + ('_' + режим if режим else ''), time.strftime('%d%m-%H%M')))
    питон = ПИТОН_ПАНЕЛИ if файл == 'pilot_pasport.py' and os.path.exists(ПИТОН_ПАНЕЛИ) else sys.executable
    cmd = [питон, '-u', os.path.join(DIR, файл), '--nabor=' + НАБОР, '--shag=' + файл + ('_hvost' if режим else '')]
    with open(лог, 'ab') as f:
        if фоном:
            фон[шаг] = subprocess.Popen(cmd, cwd=DIR, env=env_шага(шаг), stdout=f, stderr=subprocess.STDOUT)
            статус()
            return None
        r = subprocess.run(cmd, cwd=DIR, env=env_шага(шаг), stdout=f, stderr=subprocess.STDOUT)
    o['шаги'][к].update({'конец': time.strftime('%Y-%m-%d %H:%M'), 'код': r.returncode,
                         'хвост': io.open(лог, encoding='utf-8', errors='replace').read()[-500:]})
    статус()
    return r.returncode


def ждать(*шаги):
    while any(фон[ш].poll() is None for ш in шаги if ш in фон):
        статус()
        time.sleep(30)


def main():
    time.sleep(60)
    while идёт('*server\\kc_kontakty.py*'):
        o['ждём'] = 'обход ещё идёт ' + time.strftime('%H:%M')
        статус()
        time.sleep(30)
    o.pop('ждём', None)
    к = [x for x in o['шаги'] if x.endswith(' kc_kontakty.py')]
    if к and not o['шаги'][к[0]].get('конец'):
        o['шаги'][к[0]].update({'конец': time.strftime('%Y-%m-%d %H:%M'), 'код': 0})
    пуск('pilot_dop_proverka.py', фоном=True)
    пуск('pilot_pasport.py', фоном=True)
    for ш in ('kc_audit.py', 'kc_audit2.py', 'kc_sayt_proverka.py', 'kc_oproverzhenie.py', 'kc_glubokiy_vhod.py'):
        if пуск(ш) != 0:
            пуск(ш)  # один повтор, как в оркестраторе
    пуск('kc_agent_glubokiy.py', фоном=True)
    пуск('kc_agent_glubokiy.py:хвост', фоном=True)
    ждать('kc_agent_glubokiy.py', 'kc_agent_glubokiy.py:хвост')
    п = os.path.join(DIR, НАБОР + '-' + ЛУНА)
    if os.path.exists(п):
        строки = [s for s in io.open(п, encoding='utf-8', errors='replace') if s.strip()]
        with io.open(os.path.join(DIR, НАБОР + '-glubokiy.jsonl'), 'a', encoding='utf-8') as f:
            for s in строки:
                f.write(s if s.endswith('\n') else s + '\n')
            f.flush()
            os.fsync(f.fileno())
        os.rename(п, п + '.слит')
        o['слито_луна'] = len(строки)
    ждать('pilot_dop_proverka.py', 'pilot_pasport.py')
    пуск('kc_agent_pereproverka.py')
    for ф in (НАБОР + x for x in ('-razbor.jsonl', '-spisok.json', '-reestr.json', '-zenka.json', '-kontakty.jsonl',
                                   '-audit.jsonl', '-audit2.jsonl', '-sayt-proverka.jsonl', '-oprov.jsonl', '-glubokiy.jsonl',
                                   '-glubokiy2.jsonl', '-serp.jsonl', '-dop.jsonl', '-sayty-dobor.jsonl', '-klass.jsonl',
                                   '-pasport.jsonl')):
        if os.path.exists(os.path.join(DIR, ф)):
            shutil.copyfile(os.path.join(DIR, ф), os.path.join(ДРОП, ф))
    o['конец'] = time.strftime('%Y-%m-%d %H:%M')
    статус()


if __name__ == '__main__':
    main()
