# -*- coding: utf-8 -*-
# 19.10: конвейер kc1 остановился на шаге kc_audit2 (после агентов, лог пустой, процесса нет). Добить оставшиеся шаги
# «после агентов» (kc_audit2, kc_sayt_proverka, kc_oproverzhenie — все резюмируемые) и скопировать итоговые файлы на дроп.
# Плюс компактная копия контактов для Excel: kc1-kontakty.jsonl на сервере 600 МБ (дописывался прогонами) — на дроп кладём
# последнюю запись по ИНН с итогом ok (kc1-kontakty-slim.jsonl).
import io, json, os, shutil, subprocess, sys, time
DIR = r'C:\sender\server'
ДРОП = r'C:\seostat\drop\drop-storage'
os.environ.update({'POISK_NABOR': 'kc1', 'KC_NABOR': 'kc1', 'POISK_REGIONY_SVERKI': 'все', 'KC_CEL': 'kc', 'PILOT_VOLNY': '1',
                   'KC_EC': '1', 'KC_EC_XML_OT': '5e8', 'KC_EC_BEZ_MODELI': '1', 'KC_LIMIT_MIN': '25', 'KC_POTOKOV': '48',
                   'KC_AGENT_XML_MIN': '60', 'PILOT_MODEL': 'gpt-6-luna', 'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna',
                   'PYTHONIOENCODING': 'utf-8'})
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'kc1_dobit_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_kc1_dobit.py'), '--vnutri'], cwd=DIR,
                             creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(20)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-500:]},
                     ensure_ascii=False))
    sys.exit(0)


def п(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def слим():
    посл = {}
    for s in io.open(os.path.join(DIR, 'kc1-kontakty.jsonl'), encoding='utf-8', errors='replace'):
        try:
            x = json.loads(s)
        except ValueError:
            continue
        if x.get('inn') and x.get('итог') == 'ok':
            посл[x['inn']] = s
    вых = os.path.join(ДРОП, 'kc1-kontakty-slim.jsonl')
    with io.open(вых, 'w', encoding='utf-8') as f:
        f.writelines(посл.values())
        f.flush()
        os.fsync(f.fileno())
    п('контакты: компаний', len(посл), '->', вых)


слим()
import pilot_konveyer as PK  # noqa: E402
w = PK.Волны()
for файл in ('kc_audit2.py', 'kc_sayt_proverka.py', 'kc_oproverzhenie.py'):
    t0 = time.time()
    r = subprocess.run([PK.питон(файл), '-u', os.path.join(DIR, файл), '--metka=kc1dobit_' + файл[:-3]], cwd=DIR,
                       env=w.env_шага(файл), capture_output=True, text=True, errors='replace')
    п(файл, 'код', r.returncode, 'за %.1f мин' % ((time.time() - t0) / 60), '|', (r.stdout + r.stderr)[-400:].replace('\n', ' | '))
слим()
for ф in ('-spisok.json', '-audit.jsonl', '-audit2.jsonl', '-sayt-proverka.jsonl', '-oprov.jsonl', '-glubokiy.jsonl',
          '-glubokiy2.jsonl', '-pasport.jsonl', '-zenka.json', '-reestr.json', '-razbor.jsonl', '-klass.jsonl', '-dop.jsonl',
          '-chuzhie.jsonl'):
    try:
        shutil.copyfile(os.path.join(DIR, 'kc1' + ф), os.path.join(ДРОП, 'kc1' + ф))
    except Exception as e:  # noqa: BLE001
        п('копия', ф, repr(e)[:80])
п('KC1 ДОБИТ')
