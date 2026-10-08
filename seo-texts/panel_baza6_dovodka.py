# -*- coding: utf-8 -*-
"""База 6, доводка карточки после просмотра.
1. Именованные не-ЛПР (начальник автоколонны, ВЭД, логистика…) поднимались наверх рядом с
   ЛПР: верхний блок берёт «есть роль ИЛИ названо имя». Неличный номер, который каталог
   увёл вниз, имя больше не поднимает. Свёртка подписана честно: «Остальные номера».
2. «Чем связана» в составе холдинга перечисляла все общие номера (у MLK Group – 11 подряд):
   теперь «общих номеров с группой: N» и «холдинг по сайту»."""
import io, os, re, shutil, sqlite3, subprocess, sys, time
VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
RCS = os.path.join(KOREN, 'app', 'api', 'routes_centro_sales.py')
C = os.path.join(KOREN, 'app', 'templates', 'centro.html')
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
PORT = 8016
B = os.path.join(KOREN, '_bekap', time.strftime('baza6-dovodka-%Y%m%d-%H%M%S'))
os.makedirs(B, exist_ok=True)
for p, staro, novo, priznak in (
    (RCS, '''            def _наверх(item):
                return bool(item.get("has_role")) or bool(
                    str(item.get("person") or "").strip())''',
     '''            def _наверх(item):
                # неличный номер, который каталог увёл вниз, имя не поднимает (База 6:
                # «начальник автоколонны» с фамилией не должен стоять рядом с ЛПР)
                if str(item.get("nomer_ne_lichnyy") or "").strip() and not item.get("has_role"):
                    return False
                return bool(item.get("has_role")) or bool(
                    str(item.get("person") or "").strip())''', 'имя не поднимает'),
    (C, '<summary>Безымянные номера без роли ({{ unassigned_contacts|length }})</summary>',
     '<summary>Остальные номера: без роли или не ЛПР ({{ unassigned_contacts|length }})</summary>',
     'Остальные номера: без роли или не ЛПР')):
    t = io.open(p, encoding='utf-8').read()
    if priznak in t:
        print('[уже] %s' % os.path.basename(p))
    elif t.count(staro) == 1:
        shutil.copy2(p, os.path.join(B, os.path.basename(p)))
        io.open(p, 'w', encoding='utf-8').write(t.replace(staro, novo, 1))
        print('[ок] %s' % os.path.basename(p))
    else:
        print('[ЯКОРЬ: %d] %s' % (t.count(staro), os.path.basename(p)))
        raise SystemExit(1)
k = sqlite3.connect(KAT)
src = sqlite3.connect(os.path.join(B, 'meyer_baza1.db'))
k.backup(src)
src.close()
n = 0
for rid, svyaz in k.execute('select rowid, svyaz from holding_chlen').fetchall():
    chasti = []
    obshch = len(re.findall(r'общий номер', svyaz or ''))
    if obshch:
        chasti.append('общих номеров с группой: %d' % obshch)
    if 'холдинг по сайту' in (svyaz or ''):
        chasti.append('холдинг по сайту')
    novo = ', '.join(chasti)
    if novo != svyaz:
        k.execute('update holding_chlen set svyaz=? where rowid=?', (novo, rid))
        n += 1
k.commit()
print('состав холдингов: подпись связи сокращена у %d строк' % n)
sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
for l in p.stdout.decode('cp866', 'replace').splitlines():
    if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
        subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
time.sleep(2)
lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
lg.write('\n===== перезапуск: доводка карточки Базы 6 %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
lg.flush()
subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg, stderr=subprocess.STDOUT,
                 creationflags=0x00000008 | 0x00000200, close_fds=True, env=sreda)
time.sleep(10)
bekap = io.open(os.path.join(KOREN, '_bekap', 'baza6-poslednyaya.txt'), encoding='utf-8').read().strip()
r = subprocess.run([VENV, r'C:\sender\_ops\3s_baza6_zalit.py', '--proverka', bekap], capture_output=True,
                   timeout=1200, cwd=KOREN, env=sreda)
print(r.stdout.decode('utf-8', 'replace')[-1200:])
if r.returncode:
    print(r.stderr.decode('utf-8', 'replace')[-2500:])
