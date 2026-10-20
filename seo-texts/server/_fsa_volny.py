# -*- coding: utf-8 -*-
# 20.10, владелец: (1) «1 480, которые Meyer (120–500 млн, уникальные, без сделок), запускай потом на остаток средств провайдера
# и хмлривера, без запасов, от большей к меньшей выручке»; (2) «глубокий поиск обновляет паспорт? если не обновляет — сделай
# прогон для паспорта, а для новых — чтобы обновлял сразу». Агенты kc_agent_glubokiy пишут только сайт и контакты; паспорт
# (pilot_pasport -> site_facts в enrich.db) строится из кэша страниц обхода kc_kontakty. Поэтому после агентов каждой волны —
# «досбор»: компании, у которых агент подтвердил сайт завода (ИНН/название на сайте) или сайт холдинга (цитата на странице),
# -> набор <волна>p: обход kc_kontakty (15 стр. + люди, ещё контакты) и паспорт pilot_pasport.
# Порядок: ждём волну fsa500 (_pusk_fsa500.py) -> досбор fsa500p параллельно с агентами fsa120 -> досбор fsa120p.
# Агенты fsa120: Sol, сначала крупные (kc_agent_glubokiy сортирует по выручке), xmlriver до остатка 1 ₽; провайдер — сторож:
# 3 неудачных пробных вызова подряд (баланс шлюза кончился) -> агентов остановить, xmlriver не жечь вслепую.
# Durable: <набор>-glubokiy.jsonl, <набор>p-kontakty.jsonl, site_facts (enrich.db) — у всех шагов резюм. Лог: fsa_volny_*.log.
import json, os, shutil, subprocess, sys, threading, time
DIR = r'C:\sender\server'
ДРОП = r'C:\seostat\drop\drop-storage'
ПИТОН_ПАНЕЛИ = r'C:\Program Files\Python311\python.exe'
if __name__ == '__main__' and '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'fsa_volny_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_fsa_volny.py'), '--vnutri'], cwd=DIR,
                             creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(30)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-700:]},
                     ensure_ascii=False))
    sys.exit(0)
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
ОБЩЕЕ = {'KC_CEL': 'meyer', 'POISK_REGIONY_SVERKI': 'все', 'PILOT_VOLNY': '1', 'KC_EC': '1', 'KC_EC_XML_OT': '5e8',
         'KC_EC_BEZ_MODELI': '1', 'KC_LIMIT_MIN': '25', 'KC_POTOKOV': '32', 'KC_MODEL_PARALLEL': '24', 'KC_PROTSESSOV': '4',
         'PILOT_MODEL': 'gpt-6-luna', 'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna', 'PYTHONIOENCODING': 'utf-8'}


def п(*a):
    print(time.strftime('%d.%m %H:%M:%S'), *a, flush=True)


def идёт(метка):
    r = subprocess.run(['wmic', 'process', 'where', "name='python.exe'", 'get', 'CommandLine'], capture_output=True, text=True, errors='replace')
    return any(метка in x for x in r.stdout.splitlines() if 'wmic' not in x)


def читать(путь):
    out = {}
    if os.path.exists(путь):
        for s in open(путь, encoding='utf-8', errors='replace'):
            try:
                x = json.loads(s)
                out[x['inn']] = x
            except (ValueError, KeyError):
                pass
    return out


def запуск(файл, env, метка, питон=sys.executable):
    лог = os.path.join(DIR, 'fsa_volny_%s_%s.log' % (метка, time.strftime('%d%m-%H%M')))
    with open(лог, 'wb') as ф:
        return subprocess.Popen([питон, '-u', os.path.join(DIR, файл), '--metka=' + метка], cwd=DIR, env=env,
                                stdin=subprocess.DEVNULL, stdout=ф, stderr=subprocess.STDOUT), лог


def хвост(лог, n=400):
    return open(лог, encoding='utf-8', errors='replace').read()[-n:].replace('\n', ' | ')


def досбор(волна):
    """Сайты, подтверждённые агентами волны -> набор <волна>p: обход + паспорт."""
    сп = json.load(open(os.path.join(DIR, волна + '-spisok.json'), encoding='utf-8'))['компании']
    нов = {}
    for инн, x in читать(os.path.join(DIR, волна + '-glubokiy.jsonl')).items():
        сайт = (x.get('сайт_завода') if x.get('сайт_завода_чей') else '') or (x.get('сайт_холдинга') if x.get('холдинг_подтверждён') else '')
        if сайт and инн in сп:
            нов[инн] = dict(сп[инн], сайт=сайт, сайт_откуда='агент глубокого поиска: ' + (x.get('сайт_завода_чей') or 'сайт холдинга'))
    набор = волна + 'p'
    with open(os.path.join(DIR, набор + '-spisok.json'), 'w', encoding='utf-8') as f:
        json.dump({'компании': нов, 'снято': {}, 'ниже_порога': {}, 'на_решение': {}}, f, ensure_ascii=False)
    п(набор, 'компаний с сайтом от агентов', len(нов))
    if not нов:
        return
    env = dict(os.environ, **ОБЩЕЕ, POISK_NABOR=набор, KC_NABOR=набор, PROVIDER_MODEL='gpt-6-luna')
    for файл, питон in (('kc_kontakty.py', sys.executable), ('pilot_pasport.py', ПИТОН_ПАНЕЛИ if os.path.exists(ПИТОН_ПАНЕЛИ) else sys.executable)):
        t0 = time.time()
        pr, лог = запуск(файл, env, набор + '_' + файл[:-3], питон)
        pr.wait()
        п(набор, файл, 'код', pr.returncode, 'за %.1f мин' % ((time.time() - t0) / 60), '|', хвост(лог))
    for ф in ('-kontakty.jsonl', '-pasport.jsonl', '-spisok.json'):
        try:
            shutil.copyfile(os.path.join(DIR, набор + ф), os.path.join(ДРОП, набор + ф))
        except Exception as e:  # noqa: BLE001
            п('копия', набор + ф, repr(e)[:80])


def провайдер_жив():
    import verify_company as VC
    for _ in range(3):
        try:
            if VC._provider_call_stdlib('Ответь одним словом: ок', model='gpt-6-sol'):
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(60)
    return False


def агенты(волна):
    shutil.copyfile(os.path.join(ДРОП, волна + '-spisok.json'), os.path.join(DIR, волна + '-spisok.json'))
    env = dict(os.environ, KC_NABOR=волна, KC_CEL='meyer', PROVIDER_MODEL='gpt-6-sol', KC_AGENT_POTOKOV='30',
               KC_XML_KANALOV='4', KC_AGENT_XML_MIN='1', KC_MODEL_PARALLEL='30', PYTHONIOENCODING='utf-8')
    t0 = time.time()
    pr, лог = запуск('kc_agent_glubokiy.py', env, волна + '_agenty')
    while pr.poll() is None:
        time.sleep(180)
        if pr.poll() is None and not провайдер_жив():
            п(волна, 'провайдер не отвечает 3 раза подряд (баланс?) — агентов останавливаю')
            subprocess.run(['taskkill', '/PID', str(pr.pid), '/T', '/F'], capture_output=True)
            break
    п(волна, 'агенты: код', pr.returncode, 'за %.1f ч' % ((time.time() - t0) / 3600), '|', хвост(лог))
    try:
        shutil.copyfile(os.path.join(DIR, волна + '-glubokiy.jsonl'), os.path.join(ДРОП, волна + '-glubokiy.jsonl'))
    except Exception as e:  # noqa: BLE001
        п('копия', repr(e)[:80])


if __name__ == '__main__':  # 20.10: модуль импортирует _fsa_deshevo (досбор, запуск) — без побочных запусков
    п('жду волну fsa500')
    while идёт('_pusk_fsa500.py') or идёт('KC_NABOR=fsa500'):
        time.sleep(120)
    try:
        shutil.copyfile(os.path.join(DIR, 'fsa500-glubokiy.jsonl'), os.path.join(ДРОП, 'fsa500-glubokiy.jsonl'))
    except Exception as e:  # noqa: BLE001
        п('копия fsa500', repr(e)[:80])
    п('волна fsa500 закончена: агентов', len(читать(os.path.join(DIR, 'fsa500-glubokiy.jsonl'))))
    т = threading.Thread(target=досбор, args=('fsa500',))
    т.start()
    агенты('fsa120')
    т.join()
    досбор('fsa120')
    п('ВОЛНЫ ГОТОВЫ')
