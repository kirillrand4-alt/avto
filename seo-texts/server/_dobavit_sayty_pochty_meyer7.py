# -*- coding: utf-8 -*-
# 12.10, владелец: «добавь те 25 вероятных сайтов из почты». Компании без подтверждённого сайта, у которых домен
# корпоративной почты (база обзвона/Checko/ЛПР/контакты) открылся и на нём ИНН (1) или название компании (25)
# (meyer7-bez-sayta-proverka.jsonl). 1) сайт — в список (под замком, бэкап, прежний сайт — «сайт_был»); 2) ждать конца
# конвейера допоиска (один писатель файла обхода); 3) конвейер контактов по ним (KC_TOLKO_INN). Лог: konveyer_meyer7_pochta_sayty_*.log
import io, json, os, shutil, subprocess, sys, time
DIR = r'C:\sender\server'
os.environ.update({
    'POISK_NABOR': 'meyer7', 'KC_NABOR': 'meyer7', 'POISK_REGIONY_SVERKI': 'все', 'PILOT_VOLNY': '1',
    'KC_EC': '1', 'KC_EC_XML_OT': '5e8', 'KC_EC_BEZ_MODELI': '1', 'KC_LIMIT_MIN': '25',
    'KC_POTOKOV': '96', 'KC_MODEL_PARALLEL': '32', 'KC_PROTSESSOV': '6',
    'PILOT_SAYTY_MAX': '24000', 'KC_AGENT_XML_MIN': '60',
    'PILOT_MODEL': 'gpt-6-luna', 'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna', 'PYTHONIOENCODING': 'utf-8'})
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'konveyer_meyer7_pochta_sayty_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR, creationflags=0x08 | 0x200,
                             stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(25)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-1500:]},
                     ensure_ascii=False))
    sys.exit(0)
import zamok  # noqa: E402


def п(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


ПОРЯДОК = ['подтверждён: ИНН компании на сайте', 'вероятно: название компании на сайте']
лучш = {}
for s in io.open(os.path.join(DIR, 'meyer7-bez-sayta-proverka.jsonl'), encoding='utf-8'):
    r = json.loads(s)
    if r['класс'] in ПОРЯДОК and (r['inn'] not in лучш or ПОРЯДОК.index(r['класс']) < ПОРЯДОК.index(лучш[r['inn']]['класс'])):
        лучш[r['inn']] = r
СП = os.path.join(DIR, 'meyer7-spisok.json')
ключи = []
with zamok.замок(СП):
    сп = zamok.прочитать(СП)
    shutil.copyfile(СП, СП + '.bak-pochta-' + time.strftime('%d%m-%H%M'))
    for i, r in лучш.items():
        к = сп['компании'].get(i)
        if not к:
            п('нет в списке', i, r['имя'])
            continue
        к['сайт_был'] = к.get('сайт') or ''
        к['сайт'] = 'https://' + r['домен'] + '/'
        к['сайт_откуда'] = '12.10: домен корпоративной почты (база обзвона/Checko/ЛПР); на сайте %s' % (
            'ИНН компании' if r['класс'].startswith('подтверждён') else 'название компании')
        ключи.append(i)
        п('сайт', i, r['имя'][:40], '->', r['домен'], '| был:', к['сайт_был'] or '-')
    zamok.записать_атомарно(СП, сп)
СПИСОК_ИНН = os.path.join(DIR, 'meyer7-pochta-sayty-inn.txt')
with io.open(СПИСОК_ИНН, 'w', encoding='utf-8') as f:
    f.write('\n'.join(ключи) + '\n')
    f.flush()
    os.fsync(f.fileno())
п('в список сайтов:', len(ключи))


def идут(*метки):
    r = subprocess.run(['wmic', 'process', 'where', "name='python.exe'", 'get', 'CommandLine'], capture_output=True,
                       text=True, errors='replace')
    return [м for м in метки if any(м in x for x in r.stdout.splitlines())]


while идут('_dobavit_dopoisk_meyer7', 'dopoisk_kc_', 'dopoisk_pilot_', '_pusk_meyer7_pereobhod'):
    time.sleep(60)
п('конвейер допоиска закончен')
import pilot_konveyer as PK  # noqa: E402
w = PK.Волны()


def шаг(файл, доп=None):
    env = dict(w.env_шага(файл), **(доп or {}))
    t0 = time.time()
    r = subprocess.run([PK.питон(файл), '-u', os.path.join(DIR, файл), '--metka=pochta_sayty_' + файл[:-3]], cwd=DIR,
                       env=env, capture_output=True, text=True, errors='replace')
    п(файл, 'код', r.returncode, 'за %.1f мин' % ((time.time() - t0) / 60), '|', (r.stdout + r.stderr)[-400:].replace('\n', ' | '))


ТОЛЬКО = {'KC_TOLKO_INN': СПИСОК_ИНН}
шаг('kc_kontakty.py')
шаг('kc_doizvlech.py')
шаг('kc_doizvlech_pochty.py', ТОЛЬКО)
шаг('kc_skrytye.py', dict(ТОЛЬКО, KC_SKRYTYE_PROBA='0'))
шаг('kc_doobhod.py', ТОЛЬКО)
шаг('kc_doobhod.py', dict(ТОЛЬКО, KC_DOOBHOD_SHIROKO='1'))
шаг('kc_dorazmetka.py')
шаг('kc_audit.py')
шаг('kc_sayt_proverka.py')
for ф in ('-kontakty.jsonl', '-spisok.json', '-audit.jsonl', '-sayt-proverka.jsonl'):
    try:
        shutil.copyfile(os.path.join(DIR, 'meyer7' + ф), os.path.join(PK.ДРОП, 'meyer7' + ф))
    except Exception as e:  # noqa: BLE001
        п('копия', ф, repr(e)[:80])
п('САЙТЫ ИЗ ПОЧТЫ ГОТОВО')
