# -*- coding: utf-8 -*-
# 12.10, владелец: сделки — только АКТИВНЫЕ сделки Meyer («проигранным можно и писать и звонить снова»; «сделки КЦ не надо
# снимать, мы готовим под Meyer»). Отбор снял 1015 компаний по запрету панели «идёт сделка» — 635 активны в Meyer (остаются
# снятыми), 380 возвращаются (97 проиграны, 8 успешны и закрыты, 275 — сделки КЦ/нет в выгрузке Meyer). Их сняли до поиска
# сайтов — для них конвейер целиком (без агентов и аудита-2), последовательно, одним писателем файла обхода.
# Список ИНН — meyer7-vozvrat-sdelki.json (с локальной сверки выгрузки Битрикс). Лог: konveyer_meyer7_vozvrat_sdelki_*.log.
# 12.10 06:40, версия 2: 1-я версия вернула 380 в список (05:49), но поиск сайтов (pilot_sayty_dobor) без фильтра искал
# всем компаниям без сайта (~690/ч, возвращённые вперемешку) — 1-я версия останавливается, шаги заново, поиск сайтов
# только по 380 (KC_TOLKO_INN). Возврат в список повторно не делается (идемпотентно: снятых уже нет).
import io, json, os, shutil, subprocess, sys, time
DIR = r'C:\sender\server'
os.environ.update({  # окружение оркестратора финала (как _pusk_meyer7_final_s_obhoda.py)
    'POISK_NABOR': 'meyer7', 'KC_NABOR': 'meyer7', 'POISK_REGIONY_SVERKI': 'все', 'PILOT_VOLNY': '1',
    'KC_EC': '1', 'KC_EC_XML_OT': '5e8', 'KC_EC_BEZ_MODELI': '1', 'KC_LIMIT_MIN': '25',
    'KC_POTOKOV': '96', 'KC_MODEL_PARALLEL': '32', 'KC_PROTSESSOV': '6',
    'PILOT_SAYTY_MAX': '24000', 'KC_AGENT_XML_MIN': '60',
    'PILOT_MODEL': 'gpt-6-luna', 'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna', 'PYTHONIOENCODING': 'utf-8'})
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)

if '--vnutri' not in sys.argv:
    # остановить 1-ю версию (родитель и его текущий шаг); журналы шагов — построчно с fsync, список — атомарно
    r = subprocess.run(['wmic', 'process', 'where', "name='python.exe'", 'get', 'ProcessId,CommandLine'],
                       capture_output=True, text=True, errors='replace')
    убиты = []
    for x in r.stdout.splitlines():
        if ('_vozvrat_sdelki_meyer7.py' in x or '--metka=vozvrat_sdelki_' in x) and '_vozvrat_sdelki_meyer7_2' not in x \
                and 'vozvrat2_' not in x:
            pid = x.strip().split()[-1]
            if pid.isdigit():
                subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True)
                убиты.append((pid, x.strip()[-70:]))
    time.sleep(5)
    лог = os.path.join(DIR, 'konveyer_meyer7_vozvrat2_sdelki_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri', '--metka=vozvrat2_meyer7'],
                             cwd=DIR, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в,
                             stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(30)
    print('===ИТОГ===')
    print(json.dumps({'остановлены': убиты, 'pid': p.pid, 'лог': os.path.basename(лог),
                      'хвост': open(лог, encoding='utf-8', errors='replace').read()[-600:]}, ensure_ascii=False, indent=1))
    sys.exit(0)

import pilot_konveyer as PK  # noqa: E402
import zamok  # noqa: E402


def п(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


СП = os.path.join(DIR, 'meyer7-spisok.json')
инн = json.load(io.open(os.path.join(DIR, 'meyer7-vozvrat-sdelki.json'), encoding='utf-8'))
сп = zamok.прочитать(СП)
п('в списке из возвращённых', sum(1 for i in инн if i in сп['компании']), 'из', len(инн),
  '| с сайтом', sum(1 for i in инн if (сп['компании'].get(i) or {}).get('сайт')))
del сп
СПИСОК_ИНН = os.path.join(DIR, 'meyer7-vozvrat-inn.txt')
with io.open(СПИСОК_ИНН, 'w', encoding='utf-8') as f:
    f.write('\n'.join(инн) + '\n')
    f.flush()
    os.fsync(f.fileno())
w = PK.Волны()


def шаг(файл, доп=None):
    env = dict(w.env_шага(файл), **(доп or {}))
    t0 = time.time()
    r = subprocess.run([PK.питон(файл), '-u', os.path.join(DIR, файл), '--metka=vozvrat2_' + файл[:-3]], cwd=DIR,
                       env=env, capture_output=True, text=True, errors='replace')
    п(файл, 'код', r.returncode, 'за %.1f мин' % ((time.time() - t0) / 60), '|', (r.stdout + r.stderr)[-500:].replace('\n', ' | '))
    return r.returncode


ТОЛЬКО = {'KC_TOLKO_INN': СПИСОК_ИНН}
шаг('pilot_sayty_dobor.py', ТОЛЬКО)
шаг('kc_kontakty.py')
шаг('kc_doizvlech.py')
шаг('kc_doizvlech_pochty.py', ТОЛЬКО)
шаг('kc_skrytye.py', dict(ТОЛЬКО, KC_SKRYTYE_PROBA='0'))
шаг('kc_doobhod.py', ТОЛЬКО)
шаг('kc_dorazmetka.py')
шаг('pilot_dop_proverka.py')
шаг('kc_audit.py')
шаг('kc_sayt_proverka.py')
шаг('kc_oproverzhenie.py')
шаг('pilot_pasport.py')
шаг('kc_gruppy.py', {'PROVIDER_MODEL': 'gpt-6-luna'})
for ф in ('-kontakty.jsonl', '-spisok.json', '-audit.jsonl', '-sayt-proverka.jsonl', '-oprov.jsonl', '-pasport.jsonl',
          '-gruppy.jsonl', '-sayty-dobor.jsonl', '-dop.jsonl'):
    try:
        shutil.copyfile(os.path.join(DIR, 'meyer7' + ф), os.path.join(PK.ДРОП, 'meyer7' + ф))
    except Exception as e:  # noqa: BLE001
        п('копия', ф, repr(e)[:80])
п('ВОЗВРАТ ГОТОВ')  # версия 2
