# -*- coding: utf-8 -*-
# 21.10, владелец «проверь выборку 40 компаний, что это именно их сайты» (Luna fsa120L): независимая проверка 40 —
# свой 17, нельзя понять 16, группа 3, чужой 4; по «сайту холдинга» своих 0 из 10. Сайты агентов в досборе (наборы <волна>p)
# опровергатель не проверял — только «ИНН/название на сайте» со слов агента. Здесь: опровергатель (kc_oproverzhenie, Luna)
# по наборам fsa500p и fsa1000p сразу, по fsa120Lp — после досбора Luna (ждём _fsa120_luna.py). Сборка fsa_vse_xlsx берёт
# «опровергаю» -> сайт не компании, «сомневаюсь» -> вероятный. Durable: <набор>-oprov.jsonl (резюм) -> дроп. Лог: p_oprov_*.log.
import os, subprocess, sys, threading, time
DIR = r'C:\sender\server'
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'p_oprov_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_p_oprov.py'), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(30)
    print('===ИТОГ===', open(лог, encoding='utf-8', errors='replace').read()[-500:])
    sys.exit(0)
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import _fsa_volny as V  # noqa: E402
import _fsa_noch as N  # noqa: E402

ШАГ = (('kc_oproverzhenie.py', {}),)
пп = [threading.Thread(target=N.конвейер, args=(н, 'meyer', ШАГ)) for н in ('fsa500p', 'fsa1000p')]
for п in пп:
    п.start()
V.п('жду Luna fsa120 (агенты + досбор)')
while V.идёт('_fsa120_luna.py'):
    time.sleep(300)
N.конвейер('fsa120Lp', 'meyer', ШАГ)
for п in пп:
    п.join()
V.п('ОПРОВЕРГАТЕЛИ p: ГОТОВО')
