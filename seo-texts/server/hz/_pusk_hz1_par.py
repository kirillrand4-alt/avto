# -*- coding: utf-8 -*-
# 20.10, параллельная ветка (владелец: «параллельно не получится?»): проверка сайта и опровергатели только читают
# hz1-kontakty — идут рядом с последовательной цепочкой доизвлечения _pusk_hz1.py. Шапка ниже — общая.
# Исходно: «прогнать весь конвейер по известным доменам… тот, где до 40 страниц открывается» — база холодного
# прозвона Кем/Том/Омск (листы База / Без телефона / Адрес в другом регионе): 332 компании с известным сайтом -> набор hz1,
# полный обход kc_kontakty (15 страниц + до 40 страниц людей + обогатитель с кэшем до 40), доизвлечение, скрытые номера,
# дообход, роли, аудит, проверка сайта, опровергатели. Поиск сайта по названию не нужен. Цель — лесенка КЦ (KC_CEL=kc).
# Вход: дроп hz1-spisok.json. Выходы: C:\sender\server\hz1-*.jsonl (резюм у каждого шага) + копии на дроп.
import json, os, shutil, subprocess, sys, time
DIR = r'C:\sender\server'
ДРОП = r'C:\seostat\drop\drop-storage'
os.environ.update({
    'POISK_NABOR': 'hz1', 'KC_NABOR': 'hz1', 'KC_CEL': 'kc', 'POISK_REGIONY_SVERKI': 'все', 'PILOT_VOLNY': '1',
    'KC_EC': '1', 'KC_EC_XML_OT': '5e8', 'KC_EC_BEZ_MODELI': '1', 'KC_LIMIT_MIN': '25',
    'KC_POTOKOV': '48', 'KC_MODEL_PARALLEL': '32', 'KC_PROTSESSOV': '4', 'PILOT_SAYTY_MAX': '0', 'KC_AGENT_XML_MIN': '60',
    'PILOT_MODEL': 'gpt-6-luna', 'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna', 'PYTHONIOENCODING': 'utf-8'})
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'hz', 'pusk_hz1par_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, 'hz', '_pusk_hz1_par.py'), '--vnutri'], cwd=DIR,
                             creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(20)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-500:]},
                     ensure_ascii=False))
    sys.exit(0)


def п(*a):
    print(time.strftime('%d.%m %H:%M:%S'), *a, flush=True)


СП = os.path.join(DIR, 'hz1-spisok.json')
if not os.path.exists(СП):
    shutil.copyfile(os.path.join(ДРОП, 'hz1-spisok.json'), СП)
п('компаний в hz1', len(json.load(open(СП, encoding='utf-8'))['компании']))
import pilot_konveyer as PK  # noqa: E402
w = PK.Волны()


def шаг(файл, доп=None):
    env = dict(w.env_шага(файл), **(доп or {}))
    t0 = time.time()
    r = subprocess.run([PK.питон(файл), '-u', os.path.join(DIR, файл), '--metka=hz1_' + файл[:-3]], cwd=DIR,
                       env=env, capture_output=True, text=True, errors='replace')
    п(файл, 'код', r.returncode, 'за %.1f мин' % ((time.time() - t0) / 60), '|', (r.stdout + r.stderr)[-500:].replace('\n', ' | '))
    return r.returncode



from concurrent.futures import ThreadPoolExecutor  # noqa: E402
with ThreadPoolExecutor(2) as ex:
    list(ex.map(шаг, ['kc_sayt_proverka.py', 'kc_oproverzhenie.py']))
п('HZ1 ПАРАЛЛЕЛЬНАЯ ВЕТКА ГОТОВА')
