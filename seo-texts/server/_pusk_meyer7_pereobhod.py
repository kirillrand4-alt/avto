# -*- coding: utf-8 -*-
# 12.10, владелец: «обойти все сайты, где не вытащили почт… и там где вытянули тоже переобойти, не забыв и про телефоны»;
# «с порядком согласен». Порядок:
#   1) ждать конца 1-го серверного прохода (zenka_server_obhod.py: 7745 сайтов «без контактов»/«только общие»);
#   2) 2-й проход — ВСЕ остальные компании списка с сайтом (ключ ИНН или заменитель «00…» из meyer7-zenno-surrogat.json);
#   3) ждать конца возврата 380 и широкого дообхода (один писатель файла обхода);
#   4) ждать, пока приёмник Зенки (zenno_most --priyom, раз в 5 мин) заберёт наши страницы из gotovo в кэш;
#   5) разбор: kc_skrytye режим zenka (почты И номера со страниц кэша против записи), 6 долей параллельно
#      (KC_SKRYTYE_ZENKA_OT — заново и для разобранных раньше), слияние долей одним писателем (slit_zenka);
#   6) kc_dorazmetka (роли новым контактам), kc_audit («чей»), копии на дроп. Лог: konveyer_meyer7_pereobhod_*.log.
import glob, io, json, os, re, shutil, subprocess, sys, time
DIR = r'C:\sender\server'
ZENNO = r'C:\seostat\drop\zenno'
os.environ.update({
    'POISK_NABOR': 'meyer7', 'KC_NABOR': 'meyer7', 'POISK_REGIONY_SVERKI': 'все', 'PILOT_VOLNY': '1',
    'KC_EC': '1', 'KC_EC_XML_OT': '5e8', 'KC_EC_BEZ_MODELI': '1', 'KC_LIMIT_MIN': '25',
    'KC_POTOKOV': '96', 'KC_MODEL_PARALLEL': '32', 'KC_PROTSESSOV': '6',
    'PILOT_SAYTY_MAX': '24000', 'KC_AGENT_XML_MIN': '60',
    'PILOT_MODEL': 'gpt-6-luna', 'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna', 'PYTHONIOENCODING': 'utf-8'})
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
ОТ = '2026-10-12 08:00'  # старт 1-го серверного прохода: всё, разобранное раньше, — разобрать заново

ДОЛЕЙ, ПОТОКОВ = 4, '64'  # 12.10: серверный обход — 4 процесса по 64 потока (один процесс упирается в GIL)

if '--vnutri' not in sys.argv:
    # перезапуск: прежний оркестратор (ещё ждёт 1-й проход) — остановить
    r0 = subprocess.run(['wmic', 'process', 'where', "name='python.exe'", 'get', 'ProcessId,CommandLine'],
                        capture_output=True, text=True, errors='replace')
    for x in r0.stdout.splitlines():
        if '_pusk_meyer7_pereobhod.py' in x and '--vnutri' in x:
            pid0 = x.strip().split()[-1]
            if pid0.isdigit():
                subprocess.run(['taskkill', '/F', '/PID', pid0], capture_output=True)
    лог = os.path.join(DIR, 'konveyer_meyer7_pereobhod_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri', '--metka=pereobhod_meyer7'],
                             cwd=DIR, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в,
                             stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(20)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог),
                      'хвост': open(лог, encoding='utf-8', errors='replace').read()[-400:]}, ensure_ascii=False, indent=1))
    sys.exit(0)

import pilot_konveyer as PK  # noqa: E402
import zamok  # noqa: E402


def п(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def идут(*метки):
    r = subprocess.run(['wmic', 'process', 'where', "name='python.exe'", 'get', 'CommandLine'], capture_output=True,
                       text=True, errors='replace')
    return [м for м in метки if any(м in x for x in r.stdout.splitlines() if '_pusk_meyer7_pereobhod' not in x)]


пусто = 0
while пусто < 2:  # две проверки подряд без процессов обхода (перезапуск долями — пауза в секунды)
    пусто = 0 if идут('zenka_server_obhod.py') else пусто + 1
    time.sleep(60)
п('1-й серверный проход закончен')

# 2) все остальные компании списка с сайтом
НАША = os.path.join(DIR, 'meyer7-server-ochered.txt')
ЖУР = os.path.join(DIR, 'meyer7-server-obhod.jsonl')
п_map = os.path.join(DIR, 'meyer7-zenno-surrogat.json')
карта = json.load(io.open(п_map, encoding='utf-8'))
обратно = {v: k for k, v in карта.items()}
уже = {y.split(';')[0] for y in io.open(НАША, encoding='utf-8').read().splitlines() if ';' in y}
for ж in [ЖУР] + sorted(glob.glob(os.path.join(DIR, 'meyer7-server-obhod-d*.jsonl'))):
    for s in io.open(ж, encoding='utf-8', errors='replace'):
        try:
            уже.add(json.loads(s)['ключ'])
        except (ValueError, KeyError):
            pass
сп = zamok.прочитать(os.path.join(DIR, 'meyer7-spisok.json'))['компании']
нов = []
for i, к in sorted(сп.items(), key=lambda x: -(x[1].get('выручка') or 0)):
    сайт = (к.get('сайт') or '').strip()
    if not сайт:
        continue
    if i.isdigit():
        кл = i
    else:
        кл = обратно.get(i)
        if not кл:
            кл = '00%08d' % (len(карта) + 1)
            карта[кл] = i
            обратно[i] = кл
    if кл in уже:
        continue
    уже.add(кл)
    нов.append('%s;%s;oba' % (кл, сайт if сайт.startswith('http') else 'https://' + сайт))
with io.open(п_map + '.tmp', 'w', encoding='utf-8') as f:
    json.dump(карта, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
os.replace(п_map + '.tmp', п_map)
with io.open(НАША, 'a', encoding='utf-8') as f:
    f.write('\n'.join(нов) + '\n')
    f.flush()
    os.fsync(f.fileno())
п('2-й проход: поставлено', len(нов))
t0 = time.time()
доли = [subprocess.Popen([sys.executable, '-u', os.path.join(DIR, 'zenka_server_obhod.py')], cwd=DIR, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, errors='replace',
                         env=dict(os.environ, ZS_POTOKOV=ПОТОКОВ, ZS_DOLYA='%d/%d' % (k, ДОЛЕЙ))) for k in range(ДОЛЕЙ)]
for k, д in enumerate(доли):
    out, _ = д.communicate()
    п('2-й проход доля', k, 'код', д.returncode, '|', (out or '')[-400:].replace('\n', ' | '))
п('2-й проход за %.0f мин' % ((time.time() - t0) / 60))

# 3) один писатель файла обхода
while идут('vozvrat2_', '_vozvrat_sdelki_meyer7', '_shiroko_doobhod_meyer7', 'shiroko_'):
    time.sleep(60)
п('возврат 380 и широкий дообход закончены')

# 4) приёмник забрал наши страницы из gotovo
наши = {y.split(';')[0] for y in io.open(НАША, encoding='utf-8').read().splitlines() if ';' in y}
for _ in range(90):
    ост = sum(1 for e in os.scandir(os.path.join(ZENNO, 'gotovo')) if re.match(r'\d*', e.name).group(0) in наши)
    if not ост:
        break
    time.sleep(60)
п('в gotovo наших файлов осталось', ост)

w = PK.Волны()


def шаг(файл, доп=None):
    env = dict(w.env_шага(файл), **(доп or {}))
    t1 = time.time()
    r_ = subprocess.run([PK.питон(файл), '-u', os.path.join(DIR, файл), '--metka=pereobhod_' + файл[:-3]], cwd=DIR,
                        env=env, capture_output=True, text=True, errors='replace')
    п(файл, (доп or {}).get('KC_SKRYTYE_REZHIM', ''), 'код', r_.returncode, 'за %.1f мин' % ((time.time() - t1) / 60), '|',
      (r_.stdout + r_.stderr)[-700:].replace('\n', ' | '))
    return r_.returncode


# 5) разбор долями
N = 6
t1 = time.time()
пр = []
for k in range(N):
    env = dict(w.env_шага('kc_skrytye.py'), KC_SKRYTYE_REZHIM='zenka', KC_SKRYTYE_ZENKA_OT=ОТ, KC_SKRYTYE_PROBA='0',
               KC_SKRYTYE_DOLYA='%d/%d' % (k, N))
    пр.append(subprocess.Popen([PK.питон('kc_skrytye.py'), '-u', os.path.join(DIR, 'kc_skrytye.py'),
                                '--metka=pereobhod_zenka_%d' % k], cwd=DIR, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, errors='replace'))
for k, p_ in enumerate(пр):
    out, _ = p_.communicate()
    п('разбор доля', k, 'код', p_.returncode, '|', (out or '')[-300:].replace('\n', ' | '))
п('разбор долями за %.1f мин' % ((time.time() - t1) / 60))
шаг('kc_skrytye.py', {'KC_SKRYTYE_REZHIM': 'slit_zenka'})
шаг('kc_dorazmetka.py')
шаг('kc_audit.py')
with io.open(ЖУР + '.vse', 'w', encoding='utf-8') as f:  # журналы долей — одним файлом на дроп
    for ж in [ЖУР] + sorted(glob.glob(os.path.join(DIR, 'meyer7-server-obhod-d*.jsonl'))):
        f.write(io.open(ж, encoding='utf-8', errors='replace').read())
shutil.copyfile(ЖУР + '.vse', os.path.join(PK.ДРОП, 'meyer7-server-obhod-vse.jsonl'))
for ф in ('-kontakty.jsonl', '-audit.jsonl', '-zenno-surrogat.json'):
    try:
        shutil.copyfile(os.path.join(DIR, 'meyer7' + ф), os.path.join(PK.ДРОП, 'meyer7' + ф))
    except Exception as e:  # noqa: BLE001
        п('копия', ф, repr(e)[:80])
п('ПЕРЕОБХОД ГОТОВ')
