# -*- coding: utf-8 -*-
r"""Повторный проход набора ca улучшенным сборщиком (11.11; сверка с панелью; владелец: «1,2,3,5,6 применяю, но в
вакансии не лезь»). Запускать сам в фон; ждёт конца конвейера ca (замок ca\ca_konveyer.lock), чтобы в журнале
ca-kontakty.jsonl не было двух писателей.

Кого: последняя запись компании (ok) с сайтом, и
  * сайт не открылся ни одной живой страницей (теперь — браузер, варианты адреса, 45 с), или
  * своих почт нет (Cloudflare-почты, карта сайта), или
  * ЛПР нет (карта сайта: руководство, отделы, филиалы).
Шаги (каждый резюмируется, состояние — ca\ca-dopohod-progress.json):
  1. kc_kontakty.py — KC_VERSIYA=dop1111, KC_INN_FAYL (только они), ЕИС не смотрим (повтор ЕИС — отдельно); новая запись
     беднее прежней — остаётся прежняя (kc_kontakty.одна);
  2. kc_dorazmetka.py — роли там, где модель не ответила;
  3. агент «ЛПР при известном сайте» (kc_agent_glubokiy, KC_AGENT_REZHIM=lpr) — у кого сайт открылся, а ЛПР всё ещё нет,
     от 120 млн: Sol от 500 млн, Luna 120–500 млн (решение 09.10), по очереди — один писатель; вакансии не ищет;
  4. kc_agent_pereproverka.py: ca-lpr-agent.jsonl -> ca-lpr-agent2.jsonl;
  5. выгрузки ca_vygruzka_polnaya.py и ca_vygruzka.py (+ дроп).
Только сбор контактов (холд рассылок — CLAUDE.md).
"""
import io, json, os, subprocess, sys, time

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
ДРОП = r'C:\seostat\drop\drop-storage'
ВЕРСИЯ = 'dop1111'

if '--vnutri' not in sys.argv:
    лог = os.path.join(ПАПКА, 'ca_dopohod_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'] + sys.argv[1:], cwd=DIR,
                         creationflags=0x08 | 0x200 | 0x4000, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False)
    time.sleep(15)
    print('===ИТОГ===', open(лог, encoding='utf-8', errors='replace').read()[-800:])
    sys.exit(0)

ЗАМОК = os.path.join(ПАПКА, 'ca_dopohod.lock')


def жив(pid):
    return bool(pid) and pid in subprocess.run(['tasklist', '/FI', 'PID eq %s' % pid], capture_output=True, text=True).stdout


try:
    _fd = os.open(ЗАМОК, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(_fd, str(os.getpid()).encode())
    os.close(_fd)
except FileExistsError:
    if жив(open(ЗАМОК).read().strip()):
        print('уже запущен')
        sys.exit(0)
    open(ЗАМОК, 'w').write(str(os.getpid()))

ПРОГРЕСС = os.path.join(ПАПКА, 'ca-dopohod-progress.json')
сост = json.load(open(ПРОГРЕСС, encoding='utf-8')) if os.path.exists(ПРОГРЕСС) else {'готово': []}


def отметка(**k):
    сост.update(k, обновлено=time.strftime('%Y-%m-%d %H:%M:%S'))
    with open(ПРОГРЕСС + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(сост, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(ПРОГРЕСС + '.tmp', ПРОГРЕСС)
    print(json.dumps(k, ensure_ascii=False)[:300], flush=True)


# окружение — как у ca_konveyer.py (те же модели, пороги, xmlriver-лимиты), без его волновых переопределений
ENV = dict(os.environ, POISK_NABOR='ca', KC_NABOR='ca', KC_CEL='kc', KC_POTOKOV='24', KC_LIMIT_MIN='25',
           KC_EC='1', KC_EC_XML_OT='5e8', KC_EC_BEZ_MODELI='1', KC_AGENT_XML_MIN='60', KC_XML_KANALOV='8',
           PILOT_MODEL='gpt-6-luna', PROVIDER_MODEL='gpt-6-luna', PROVIDER_FALLBACK_CHEAP='gpt-5.6-luna')


def шаг(имя, файл, env, *арг):
    if имя in сост['готово']:
        return
    отметка(этап=имя, старт=time.strftime('%H:%M'))
    with open(os.path.join(ПАПКА, 'ca_dopohod_%s_%s.log' % (имя, time.strftime('%d%m-%H%M'))), 'ab') as f:
        r = subprocess.run([sys.executable, '-u', os.path.join(DIR, файл)] + list(арг), cwd=DIR, env=env, stdout=f,
                           stderr=subprocess.STDOUT)
    if r.returncode != 0:
        отметка(этап=имя, ошибка='код %s' % r.returncode)
        raise SystemExit(1)
    сост['готово'].append(имя)
    отметка(этап=имя + ': готово')


def последние():
    посл = {}
    for s in io.open(os.path.join(DIR, 'ca-kontakty.jsonl'), encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('inn') and з.get('итог') == 'ok':
            посл[з['inn']] = з
    return посл


def признаки(з):
    ном = [x for x in з.get('номера') or [] if x.get('чей') != 'другая']
    return {'открылся': any(ст == 'ok' for _, ст in з.get('страницы') or []),
            'почта': any(x.get('почта') for x in ном),
            'лпр': any(x.get('лпр') == 'да' for x in ном)}


def main():
    while True:  # конвейер ca ещё идёт — ждём (один писатель журнала)
        п = os.path.join(ПАПКА, 'ca_konveyer.lock')
        if not (os.path.exists(п) and жив(open(п).read().strip())):
            break
        отметка(этап='жду конца конвейера ca')
        time.sleep(600)
    сп = json.load(io.open(os.path.join(DIR, 'ca-spisok.json'), encoding='utf-8'))['компании']
    ф_инн = os.path.join(ПАПКА, 'ca-dopohod-inn.json')
    if not os.path.exists(ф_инн):
        посл = последние()
        кто, сч = [], {'не открылся': 0, 'нет своих почт': 0, 'нет ЛПР': 0}
        for i, з in посл.items():
            if i not in сп or not з.get('сайт'):
                continue
            п_ = признаки(з)
            if not п_['открылся']:
                сч['не открылся'] += 1
            elif not п_['почта']:
                сч['нет своих почт'] += 1
            elif not п_['лпр']:
                сч['нет ЛПР'] += 1
            else:
                continue
            кто.append(i)
        json.dump(кто, open(ф_инн, 'w', encoding='utf-8'))
        отметка(этап='список', компаний=len(кто), **сч)
    шаг('обход', 'kc_kontakty.py', dict(ENV, KC_VERSIYA=ВЕРСИЯ, KC_INN_FAYL=ф_инн, KC_ZAKUPKI_OT='1e15',
                                       KC_PROTSESSOV='3'), '--nabor=ca', '--shag=kc_kontakty.py_dopohod')
    шаг('доразметка', 'kc_dorazmetka.py', ENV, '--nabor=ca', '--shag=kc_dorazmetka.py_dopohod')
    ф_лпр = os.path.join(ПАПКА, 'ca-lpr-vhod.json')
    if 'агент ЛПР Sol' not in сост['готово']:
        посл = последние()
        вход = {}
        for i in json.load(open(ф_инн, encoding='utf-8')):
            з = посл.get(i)
            if з and i in сп and (сп[i].get('выручка') or 0) >= 120e6:
                п_ = признаки(з)
                if п_['открылся'] and not п_['лпр']:
                    вход[i] = {'сайт': з.get('сайт') or сп[i].get('сайт') or ''}
        json.dump(вход, open(ф_лпр, 'w', encoding='utf-8'), ensure_ascii=False)
        отметка(этап='вход агентов ЛПР', компаний=len(вход),
                от_500_млн=sum(1 for i in вход if (сп[i].get('выручка') or 0) >= 5e8))
    аг = dict(ENV, KC_AGENT_REZHIM='lpr', KC_AGENT_VHOD=ф_лпр, KC_AGENT_FAYL='lpr-agent.jsonl', KC_AGENT_POTOKOV='24')
    шаг('агент ЛПР Sol', 'kc_agent_glubokiy.py', dict(аг, PROVIDER_MODEL='gpt-6-sol', KC_AGENT_OT='5e8'),
        '--nabor=ca', '--shag=kc_agent_lpr_sol')
    шаг('агент ЛПР Luna', 'kc_agent_glubokiy.py', dict(аг, PROVIDER_MODEL='gpt-6-luna', KC_AGENT_OT='120e6', KC_AGENT_DO='5e8'),
        '--nabor=ca', '--shag=kc_agent_lpr_luna')
    шаг('перепроверка ЛПР', 'kc_agent_pereproverka.py', dict(ENV, KC_PEREPROV_VH='lpr-agent.jsonl',
                                                              KC_PEREPROV_VYHOD='lpr-agent2.jsonl'))
    шаг('выгрузка полная', 'ca_vygruzka_polnaya.py', ENV)
    шаг('выгрузка', 'ca_vygruzka.py', ENV)
    отметка(этап='готово')


if __name__ == '__main__':
    try:
        main()
    finally:
        try:
            os.remove(ЗАМОК)
        except OSError:
            pass
