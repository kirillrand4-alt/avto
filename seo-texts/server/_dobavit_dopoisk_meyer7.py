# -*- coding: utf-8 -*-
# 12.10, владелец: «да, добавляй 926». Допоиск (meyer7_dopoisk.py): сайты выдачи, где модель по сниппету сказала «неясно»/
# «нет», а по ТЕКСТУ страницы — «да». 1) сразу — в список (под замком, бэкап): ключ — ИНН/УНП со страницы, если такой
# компании в списке нет, иначе «САЙТ:<домен>»; 2) ждать конца переобхода (один писатель файла обхода); 3) конвейер
# контактов по ним (как возврат 380): обход, доизвлечение, спрятанные, дообход (и широкий), роли, доп. ОКВЭД, аудит,
# проверка сайта, опровергатели, паспорт, группы; копии на дроп. Лог: konveyer_meyer7_dopoisk_v_spisok_*.log.
import glob, io, json, os, re, shutil, subprocess, sys, time
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
    лог = os.path.join(DIR, 'konveyer_meyer7_dopoisk_v_spisok_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR, creationflags=0x08 | 0x200,
                             stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(30)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-800:]},
                     ensure_ascii=False))
    sys.exit(0)

import zamok  # noqa: E402


def п(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def хост(u):
    u = re.sub(r'^[a-z]+://', '', str(u or '').strip().lower()).split('/')[0].split(':')[0]
    return u[4:] if u.startswith('www.') else u


СП = os.path.join(DIR, 'meyer7-spisok.json')
да = [json.loads(s) for s in io.open(os.path.join(DIR, 'meyer7-dopoisk-reshenie.jsonl'), encoding='utf-8') if s.strip()]
да = [x for x in да if x.get('решение') == 'да']
ключи = []
with zamok.замок(СП):
    сп = zamok.прочитать(СП)
    shutil.copyfile(СП, СП + '.bak-dopoisk-' + time.strftime('%d%m-%H%M'))
    есть = set(сп['компании']) | set(сп.get('снято') or {})
    дом_есть = {хост(к.get('сайт')) for р in ('компании', 'снято') for к in (сп.get(р) or {}).values() if к.get('сайт')}
    сч = {'добавлено': 0, 'по ИНН/УНП': 0, 'по сайту': 0, 'уже в списке (ИНН)': 0, 'уже в списке (сайт)': 0}
    for x in да:
        д = хост(x['домен'])
        if д in дом_есть:
            сч['уже в списке (сайт)'] += 1
            continue
        инн = [re.sub(r'\D', '', str(v)) for v in ([x.get('инн_модель')] + list(x.get('инн_страница') or [])) if v]
        инн = [v for v in инн if len(v) in (9, 10, 12)]
        кл = ''
        if инн:
            v = инн[0]
            кл = ('BY' + v) if len(v) == 9 else v
            if кл in есть:
                сч['уже в списке (ИНН)'] += 1
                continue
        by = д.endswith('.by') or (кл.startswith('BY'))
        if not кл:
            кл = 'САЙТ:' + д
            if кл in есть:
                сч['уже в списке (сайт)'] += 1
                continue
        сегм = (x.get('сегмент') or 'по сайту') + (' (Беларусь)' if by else (' — ИНН не определён' if кл.startswith('САЙТ:') else
                                                                          ' — по сайту (ОКВЭД не найден)'))
        сп['компании'][кл] = {
            'inn': кл, 'имя': x.get('название') or д, 'регион': 'Беларусь' if by else '', 'сайт': x.get('url') or ('https://' + д),
            'осн': '', 'все': [], 'сегм': сегм, 'сегм_как': 'беларусь' if by else ('без ИНН' if кл.startswith('САЙТ:') else 'по сайту'),
            'выручка': 0, 'выручка_откуда': 'неизвестна', 'запросы': [],
            'откуда': 'допоиск 12.10: сайт выдачи, по тексту страницы подходит (модель); по сниппету было «%s»' % x.get('по_сниппету'),
            'в_нашей_базе': 'нет', 'в_реестре': 'нет', 'огрн': '', 'примечание': (x.get('почему') or '')[:200]}
        есть.add(кл)
        дом_есть.add(д)
        ключи.append(кл)
        сч['добавлено'] += 1
        сч['по сайту' if кл.startswith('САЙТ:') else 'по ИНН/УНП'] += 1
    zamok.записать_атомарно(СП, сп)
СПИСОК_ИНН = os.path.join(DIR, 'meyer7-dopoisk-inn.txt')
with io.open(СПИСОК_ИНН, 'w', encoding='utf-8') as f:
    f.write('\n'.join(ключи) + '\n')
    f.flush()
    os.fsync(f.fileno())
п('в список:', json.dumps(сч, ensure_ascii=False))


def идут(*метки):
    r = subprocess.run(['wmic', 'process', 'where', "name='python.exe'", 'get', 'CommandLine'], capture_output=True,
                       text=True, errors='replace')
    return [м for м in метки if any(м in x for x in r.stdout.splitlines())]


while идут('_pusk_meyer7_pereobhod', 'pereobhod_'):
    time.sleep(60)
п('переобход закончен')

import pilot_konveyer as PK  # noqa: E402
w = PK.Волны()


def шаг(файл, доп=None):
    env = dict(w.env_шага(файл), **(доп or {}))
    t0 = time.time()
    r = subprocess.run([PK.питон(файл), '-u', os.path.join(DIR, файл), '--metka=dopoisk_' + файл[:-3]], cwd=DIR,
                       env=env, capture_output=True, text=True, errors='replace')
    п(файл, 'код', r.returncode, 'за %.1f мин' % ((time.time() - t0) / 60), '|', (r.stdout + r.stderr)[-500:].replace('\n', ' | '))
    return r.returncode


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
шаг('kc_oproverzhenie.py')
шаг('pilot_pasport.py')
шаг('kc_gruppy.py', {'PROVIDER_MODEL': 'gpt-6-luna'})
for ф in ('-kontakty.jsonl', '-spisok.json', '-audit.jsonl', '-sayt-proverka.jsonl', '-oprov.jsonl', '-pasport.jsonl',
          '-gruppy.jsonl'):
    try:
        shutil.copyfile(os.path.join(DIR, 'meyer7' + ф), os.path.join(PK.ДРОП, 'meyer7' + ф))
    except Exception as e:  # noqa: BLE001
        п('копия', ф, repr(e)[:80])
п('ДОПОИСК В СПИСКЕ ГОТОВ')
