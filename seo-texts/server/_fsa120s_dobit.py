# -*- coding: utf-8 -*-
# 21.10: опровергатели fsa120s шли в 10 потоков (~9 сайтов/мин, ~5 ч на 2 682) — добить с резюма в 24 потока, затем паспорт
# в 16 потоков. Запускается с меткой --kak=_fsa_deshevo.py: _fsa_noch и _fsa120_hvost ждут процесс с этим именем.
import os, subprocess, sys, time
DIR = r'C:\sender\server'
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'fsa120s_dobit_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_fsa120s_dobit.py'), '--vnutri', '--kak=_fsa_deshevo.py'], cwd=DIR,
                         creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(20)
    print('===ИТОГ===', open(лог, encoding='utf-8', errors='replace').read()[-400:])
    sys.exit(0)
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import _fsa_volny as V  # noqa: E402
набор = 'fsa120s'
env = dict(os.environ, **dict(V.ОБЩЕЕ, KC_CEL='meyer'), POISK_NABOR=набор, KC_NABOR=набор, PROVIDER_MODEL='gpt-6-luna')
for файл, доп in (('kc_oproverzhenie.py', {'KC_POTOKOV_SHAGA': '48', 'KC_MODEL_PARALLEL': '48'}), ('pilot_pasport.py', {'PASPORT_POTOKOV': '16'})):
    питон = V.ПИТОН_ПАНЕЛИ if файл == 'pilot_pasport.py' and os.path.exists(V.ПИТОН_ПАНЕЛИ) else sys.executable
    t0 = time.time()
    pr, лог = V.запуск(файл, dict(env, **доп), набор + '_' + файл[:-3], питон)
    pr.wait()
    V.п(набор, файл, 'код', pr.returncode, 'за %.1f мин' % ((time.time() - t0) / 60), '|', V.хвост(лог, 300))
import shutil  # noqa: E402
for ф in ('-kontakty.jsonl', '-audit.jsonl', '-oprov.jsonl', '-pasport.jsonl', '-spisok.json'):
    try:
        shutil.copyfile(os.path.join(DIR, набор + ф), os.path.join(r'C:\seostat\drop\drop-storage', набор + ф))
    except Exception as e:  # noqa: BLE001
        V.п('копия', набор + ф, repr(e)[:80])
V.п('fsa120s ДОБИТ')
