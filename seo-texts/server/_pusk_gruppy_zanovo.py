# -*- coding: utf-8 -*-
# 12.10, владелец: «другое предприятие группы — перенёс такие контакты владельцам?», «запусти всё». kc_gruppy разбирает группу
# один раз — новые контакты переобхода на сайтах групп (24 тыс. «другая» на сайтах с 2+ компаниями списка) не разобраны.
# Заново по всем группам в meyer7-gruppy2.jsonl (gpt-5.6-luna: gpt-6-luna лежит), потом слияние: у контакта без ответа
# модели — прежнее решение (тот же ключ), прежний файл — в .bak, новый — на его место и на дроп. Лог: konveyer_meyer7_gruppy2_*.log
import io, json, os, shutil, subprocess, sys, time
DIR = r'C:\sender\server'
sys.path.insert(0, DIR); sys.path.insert(0, r'C:\sender'); os.chdir(DIR)
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'konveyer_meyer7_gruppy2_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR, creationflags=0x08 | 0x200,
                             stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(30)
    print('===ИТОГ===', json.dumps({'pid': p.pid, 'лог': os.path.basename(лог),
                                    'хвост': open(лог, encoding='utf-8', errors='replace').read()[-400:]}, ensure_ascii=False))
    sys.exit(0)
import pilot_konveyer as PK  # noqa: E402


def п(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


НОВ, СТАР = os.path.join(DIR, 'meyer7-gruppy2.jsonl'), os.path.join(DIR, 'meyer7-gruppy.jsonl')
env = dict(PK.Волны().env_шага('kc_gruppy.py'), KC_NABOR='meyer7', KC_GRUPPY_VYHOD='meyer7-gruppy2.jsonl',
           PROVIDER_MODEL='gpt-5.6-luna', PYTHONIOENCODING='utf-8')
t0 = time.time()
r = subprocess.run([PK.питон('kc_gruppy.py'), '-u', os.path.join(DIR, 'kc_gruppy.py'), '--metka=gruppy2'], cwd=DIR, env=env,
                   capture_output=True, text=True, errors='replace')
п('kc_gruppy код', r.returncode, 'за %.0f мин' % ((time.time() - t0) / 60), '|', (r.stdout + r.stderr)[-700:].replace('\n', ' | '))


def читать(п_):
    out = {}
    if os.path.exists(п_):
        for s in io.open(п_, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
                out[з['домен']] = з
            except (ValueError, KeyError):
                pass
    return out


нов, стар = читать(НОВ), читать(СТАР)
сч = {'групп новых': len(нов), 'групп прежних': len(стар), 'контактов': 0, 'с ответом': 0, 'взято прежнее': 0, 'без решения': 0}
for д, з in нов.items():
    прежн = {x['ключ']: x for x in (стар.get(д) or {}).get('контакты', [])}
    for x in з.get('контакты', []):
        сч['контактов'] += 1
        if x.get('владелец'):
            сч['с ответом'] += 1
        elif (прежн.get(x['ключ']) or {}).get('владелец'):
            for k in ('владелец', 'почему', 'площадка'):
                if прежн[x['ключ']].get(k):
                    x[k] = прежн[x['ключ']][k]
            сч['взято прежнее'] += 1
        else:
            сч['без решения'] += 1
for д, з in стар.items():  # группы, которых в новом прогоне нет (не дошёл) — прежние
    нов.setdefault(д, з)
shutil.copyfile(СТАР, СТАР + '.bak-' + time.strftime('%d%m-%H%M'))
with io.open(СТАР + '.tmp', 'w', encoding='utf-8') as f:
    for з in нов.values():
        f.write(json.dumps(з, ensure_ascii=False) + '\n')
    f.flush()
    os.fsync(f.fileno())
os.replace(СТАР + '.tmp', СТАР)
shutil.copyfile(СТАР, os.path.join(PK.ДРОП, 'meyer7-gruppy.jsonl'))
п('слияние', json.dumps(сч, ensure_ascii=False))
п('ГРУППЫ ЗАНОВО ГОТОВО')
