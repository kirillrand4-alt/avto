# -*- coding: utf-8 -*-
"""Карточка компании без ЛПР: номера наверху, а не в свёрнутых «остальных».

Заливка Базы 6 уводила неличные номера (кадры, продажи, без подписи) в «остальные». У 109
крупных компаний ЛПР нет вовсе, и у части нет даже приёмной – верх карточки оставался
пустым («Контактов с ролью нет»), а единственный путь к ЛПР лежал в свёртке. Правило теперь:
неличные уходят вниз, ТОЛЬКО если наверху есть ЛПР или приёмная; иначе все номера наверху,
каждый с пометкой вида."""
import io, os, shutil, subprocess, sys, time
VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
CAT = os.path.join(KOREN, 'app', 'services', 'centro_catalog.py')
PORT = 8016
staro = '''        # неличный номер (продажи, бухгалтерия, общий…) – в «остальные», но с видом
        if str(item.get("nomer_ne_lichnyy") or "").strip():
            item["has_role"] = 0
        result.append(item)
    return result
'''
novo = '''        result.append(item)
    # Неличный номер (продажи, бухгалтерия, общий…) уходит в «остальные», только если
    # наверху есть кому звонить (ЛПР или приёмная). У компании без них любой номер –
    # путь к ЛПР: тогда все наверху, каждый с пометкой вида.
    def _nelichnyy(x):
        return bool(str(x.get("nomer_ne_lichnyy") or "").strip())
    est_verh = any(x["has_role"] and not _nelichnyy(x) for x in result)
    for x in result:
        if _nelichnyy(x):
            x["has_role"] = 0 if est_verh else 1
    return result
'''
t = io.open(CAT, encoding='utf-8').read()
if 'est_verh = any(' in t:
    print('уже правлено')
elif t.count(staro) == 1:
    b = os.path.join(KOREN, '_bekap', time.strftime('baza6-verh-%Y%m%d-%H%M%S'))
    os.makedirs(b, exist_ok=True)
    shutil.copy2(CAT, os.path.join(b, 'centro_catalog.py'))
    io.open(CAT, 'w', encoding='utf-8').write(t.replace(staro, novo, 1))
    print('правка внесена')
else:
    print('ЯКОРЬ: %d – не правлю' % t.count(staro))
    raise SystemExit(1)
sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
for l in p.stdout.decode('cp866', 'replace').splitlines():
    if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
        subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
time.sleep(2)
lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
lg.write('\n===== перезапуск: номера компаний без ЛПР наверху %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
lg.flush()
subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg, stderr=subprocess.STDOUT,
                 creationflags=0x00000008 | 0x00000200, close_fds=True, env=sreda)
time.sleep(10)
bekap = io.open(os.path.join(KOREN, '_bekap', 'baza6-poslednyaya.txt'), encoding='utf-8').read().strip()
r = subprocess.run([VENV, r'C:\sender\_ops\3s_baza6_zalit.py', '--proverka', bekap], capture_output=True,
                   timeout=1200, cwd=KOREN, env=sreda)
print(r.stdout.decode('utf-8', 'replace')[-3500:])
if r.returncode:
    print(r.stderr.decode('utf-8', 'replace')[-2500:])
