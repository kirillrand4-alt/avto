# -*- coding: utf-8 -*-
# Полный прогон Meyer, 10.10: продолжение ФИНАЛА с обхода новым оркестратором (прежний гасится вместе с обходом).
# Зачем: обход шёл 5–7 компаний в минуту на 15 тыс. (~1,5 суток); замер — время уходит на медленные сайты и обогатитель,
# модель не упирается. Новый код обхода: обогатитель параллельно скачиванию; потоков 96 (было 48), мест у модели 32.
# Оркестратор прежний (pilot_konveyer.Волны) — те же шаги, модели, метки и повторы, что в финале после отбора и сайтов
# по названию (они уже прошли). Прежний статус шагов сохраняется.
import io, json, os, subprocess, sys, time
DIR = r'C:\sender\server'
if '--vnutri' not in sys.argv:
    # внешний запуск: детачем — этим же файлом с меткой
    ЛОГ = os.path.join(DIR, 'meyer7_konveyer_final_%s.log' % time.strftime('%d%m-%H%M'))
    python = r'C:\Program Files\Python312\python.exe'
    if not os.path.exists(python): python = sys.executable
    выход = open(ЛОГ, 'wb')
    p = subprocess.Popen([python, '-u', os.path.abspath(__file__), '--vnutri', '--metka=konveyer_meyer7_final'], cwd=DIR,
                         creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=выход, stderr=subprocess.STDOUT,
                         close_fds=False)
    выход.close()
    time.sleep(60)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(ЛОГ),
                      'хвост': open(ЛОГ, encoding='utf-8', errors='replace').read()[-500:]}, ensure_ascii=False, indent=1))
    sys.exit(0)

os.environ.update({
    'POISK_NABOR': 'meyer7', 'KC_NABOR': 'meyer7', 'POISK_REGIONY_SVERKI': 'все', 'PILOT_VOLNY': '1',
    'KC_EC': '1', 'KC_EC_XML_OT': '5e8', 'KC_EC_BEZ_MODELI': '1', 'KC_LIMIT_MIN': '25',
    'KC_POTOKOV': '96', 'KC_MODEL_PARALLEL': '32',
    # 10.10 23:53 / 00:20: обход упирается в одно ядро на процесс (GIL); 3 процесса дали ~2× (12 компаний/мин), ядер 12
    'KC_PROTSESSOV': '6',
    'PILOT_SAYTY_MAX': '24000', 'KC_AGENT_XML_MIN': '60',
    'PILOT_MODEL': 'gpt-6-luna', 'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna'})
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import pilot_konveyer as PK  # noqa: E402

w = PK.Волны()
try:
    прежний = json.load(io.open(PK.СТАТУС, encoding='utf-8'))
    w.o.update({k: v for k, v in прежний.items() if k in ('начало', 'шаги', 'режим', 'слито_луна')})
except Exception:  # noqa: BLE001
    pass
w.o['волна'] = 'финал'
w.o['перезапуск'] = 'финал с обхода %s: 6 процессов обхода, обогатитель параллельно' % time.strftime('%d.%m %H:%M')
w.статус()


def дальше():
    код = w.пуск('kc_kontakty.py')
    if код not in (0, 'занят'):
        код = w.пуск('kc_kontakty.py')
        if код != 0:
            w.o['стоп'] = 'шаг kc_kontakty.py упал — дальше без него нельзя'
            w.статус()
            return False
    w.пуск('kc_dorazmetka.py')
    for ш in ('pilot_dop_proverka.py', 'pilot_pasport.py'):
        w.пуск(ш, фоном=True)
    for ш in ('kc_audit.py', 'kc_audit2.py', 'kc_sayt_proverka.py', 'kc_oproverzhenie.py', 'kc_glubokiy_vhod.py'):
        if w.пуск(ш) not in (0, 'занят'):
            w.пуск(ш)
    агенты = ('kc_agent_glubokiy.py', 'kc_agent_glubokiy.py:хвост')
    w.ждать(агенты)
    for ш in агенты:
        w.пуск(ш, фоном=True)
    w.ждать(агенты)
    w.слить_луну()
    w.ждать(('pilot_dop_proverka.py', 'pilot_pasport.py'))
    for ш in ('pilot_dop_proverka.py', 'pilot_pasport.py'):  # догнать компании финального обхода (резюм)
        w.пуск(ш)
    w.пуск('kc_agent_pereproverka.py')
    w.o['волна'] = 'после агентов'
    for ш in PK.ПОСЛЕ_АГЕНТОВ:
        w.пуск(ш)
    return True


if дальше():
    for ф in (PK.НАБОР + x for x in ('-razbor.jsonl', '-spisok.json', '-reestr.json', '-zenka.json', '-kontakty.jsonl',
                                       '-audit.jsonl', '-audit2.jsonl', '-sayt-proverka.jsonl', '-oprov.jsonl',
                                       '-glubokiy.jsonl', '-glubokiy2.jsonl', '-serp.jsonl', '-dop.jsonl',
                                       '-sayty-dobor.jsonl', '-klass.jsonl', '-pasport.jsonl', '-chuzhie.jsonl')):
        if os.path.exists(os.path.join(DIR, ф)):
            import shutil
            shutil.copyfile(os.path.join(DIR, ф), os.path.join(PK.ДРОП, ф))
    w.o['конец'] = time.strftime('%Y-%m-%d %H:%M')
w.статус()
