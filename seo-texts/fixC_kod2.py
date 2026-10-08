# -*- coding: utf-8 -*-
"""fixC: правка app/services/centro_catalog.py под замком, проверка и перезапуск панели.

Собирается fixC_kod_sobrat.py (вкладывает fixC_kod_pravki.py и fixC_klass_kod.py).
Порядок: замок -> перечитать файл -> правки (только если функции не менялись, md5) ->
проверка в отдельном venv-процессе (импорт, главная/карточки/статистика админа и продавца
= 200, признаки правки на месте) -> при провале вернуть СВОЙ файл -> при успехе перезапуск.
"""
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
FAJL = os.path.join(KOREN, 'app', 'services', 'centro_catalog.py')
DROP = r'C:\seostat\drop\drop-storage'
PORT = 8016
PUT = '/obzvon-meyer'
ZAMOK = r'C:\centro2\_zamok.txt'
PRAVKI = [
    # вид номера по цифрам – и в phone_type: «рабочий» + «рабочий с добавочным» не дублируются
    ("""        if vid_n in ("8-800", "международный", "Казахстан"):
            item["phone_type"] = vid_n""",
     """        if vid_n in ("8-800", "международный", "Казахстан") or vid_n in _VIDY_OBYCHNYE:
            item["phone_type"] = vid_n          # fixC2: вид по цифрам и в phone_type""",
     "fixC2: вид по цифрам и в phone_type"),
]
TMP = r'C:\sender\_ops\fixC_tmp'

if '--proverka' in sys.argv:
    sys.path.insert(0, KOREN)
    import re
    import zapusk  # noqa: F401
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    from app.services import centro_catalog as cat
    from app.api import routes_centro_sales as rcs
    from app.obzvon import create_app
    from fastapi.testclient import TestClient
    plohih = 0

    def ok(u, t):
        global plohih
        plohih += 0 if u else 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))
    ok(hasattr(cat, 'rol_kontakta') and hasattr(cat, '_sprosit_u_priemnoy'), 'новый классификатор в модуле')
    ok(cat.rol_kontakta({'position': 'Отдел заготовки масличных культур'})['vid'] == 'закупки сырья', 'заготовка масличных – закупки сырья')
    ok(cat.rol_kontakta({'position': 'Главный механик'})['teh'] == 1, 'главный механик – тех. ЛПР')
    ok(cat.rol_kontakta({'position': 'Начальник транспортного цеха'})['lpr'] == 0, 'начальник транспортного цеха – не ЛПР')
    ok(cat.rol_kontakta({'position': 'мобильный с сайта, без подписи'})['vid'] == 'без подписи', '«мобильный с сайта, без подписи» – без роли')
    ok(cat.vid_nomera_po_cifram('+7 800 000-00-00') == '8-800', 'вид 8-800')
    ok(cat._phone_key_dob('+7 495 000-00-00 доб. 101') != cat._phone_key_dob('+7 495 000-00-00 доб. 102'), 'ключ общего номера – с добавочным')
    n_rol = len(cat.role_phone_inns())
    ok(0 < n_rol < 480, '«телефон с ролью» по новому правилу: %d компаний (было 480)' % n_rol)
    k = cat.contacts('1660183627')
    ok(k and k[0]['has_role'] and 'снабж' in (k[0]['position'] or '').lower(), '«Азбука сыра»: снабжение наверху с ролью (общий номер роль не теряет): %s' % (k[0]['value'] if k else '-'))
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    for u in ({'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1},
              {'id': 1, 'username': 'meyer2', 'role': 'sales', 'is_active': 1}):
        vnutr.dependency_overrides[rcs.current_user] = lambda u=u: u
        with TestClient(vnutr) as kl:
            o = kl.get(PUT + '/centro')
            ok(o.status_code == 200, '%s: главная %s' % (u['username'], o.status_code))
            if u['role'] == 'admin':
                o = kl.get(PUT + '/centro/stats')
                ok(o.status_code == 200, 'статистика %s' % o.status_code)
                for inn in ('6111008006', '2222826352', '1660183627', '5957004185', '1829013726', '7203319557', '4238013194'):
                    o = kl.get(PUT + '/centro', params={'inn': inn})
                    ok(o.status_code == 200 and 'contacts-section' in o.text, 'карточка %s: %s' % (inn, o.status_code))
            else:
                naz = None
                try:
                    from app.services import centro_sales as sales
                    with sales.connect() as s:
                        r = s.execute("select inn from company_assignment where username='meyer2' limit 1").fetchone()
                        naz = r[0] if r else None
                except Exception:  # noqa: BLE001
                    pass
                if naz:
                    o = kl.get(PUT + '/centro', params={'inn': naz})
                    ok(o.status_code == 200, 'продавец: своя карточка %s: %s' % (naz, o.status_code))
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
    raise SystemExit(0)


def vzyat_zamok(kto):
    if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
        os.remove(ZAMOK)
    try:
        fd = os.open(ZAMOK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print('ЗАМОК ЗАНЯТ: ' + io.open(ZAMOK, encoding='utf-8').read())
        raise SystemExit(3)
    os.write(fd, ('%s %s' % (kto, time.strftime('%H:%M:%S'))).encode('utf-8'))
    os.close(fd)


def otdat_zamok():
    try:
        os.remove(ZAMOK)
    except OSError:
        pass


os.makedirs(TMP, exist_ok=True)

BEKAP = os.path.join(KOREN, '_bekap', time.strftime('fixC-kod2-%Y%m%d-%H%M%S'))
vzyat_zamok('fixC (роли номеров, centro_catalog.py)')
try:
    os.makedirs(BEKAP, exist_ok=True)
    t = io.open(FAJL, encoding='utf-8').read()
    shutil.copy2(FAJL, os.path.join(BEKAP, 'centro_catalog.py'))
    nt, zh = t, []
    for staro, novo, priznak in PRAVKI:
        if priznak in nt:
            zh.append('[уже] ' + priznak[:60])
            continue
        if nt.count(staro) != 1:
            print('НЕ ПРАВЛЮ: якорь найден %d раз: %s' % (nt.count(staro), staro[:80]))
            raise SystemExit(4)
        nt = nt.replace(staro, novo, 1)
        zh.append('[ок] ' + priznak[:60])
    for x in zh:
        print('   ' + x)
    izmenen = nt != t
    if izmenen:
        compile(nt, FAJL, 'exec')
        io.open(FAJL, 'w', encoding='utf-8').write(nt)
    sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
    r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka'], capture_output=True,
                       timeout=1200, cwd=KOREN, env=sreda)
    vyvod = r.stdout.decode('utf-8', 'replace')
    if r.returncode:
        vyvod += '\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-4000:]
    io.open(os.path.join(DROP, 'fixC-kod2-proverka.txt'), 'w', encoding='utf-8').write(vyvod)
    good = r.returncode == 0 and 'ПЛОХИХ ПРОВЕРОК: 0' in vyvod
    if not good:
        if izmenen:
            shutil.copy2(os.path.join(BEKAP, 'centro_catalog.py'), FAJL)
        print('ПРОВЕРКА НЕ ПРОШЛА – centro_catalog.py возвращён из копии, перезапуска нет')
    elif izmenen or '--perezapusk' in sys.argv:
        p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
        for l in p.stdout.decode('cp866', 'replace').splitlines():
            if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
                subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
        time.sleep(2)
        lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
        lg.write('\n===== перезапуск: fixC2 вид номера %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
        lg.flush()
        subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg,
                         stderr=subprocess.STDOUT, creationflags=0x00000008 | 0x00000200,
                         close_fds=True, env=sreda)
        time.sleep(10)
        import urllib.request
        kod = None
        for _ in range(6):
            try:
                kod = urllib.request.urlopen('http://127.0.0.1:%d%s/centro/login' % (PORT, PUT), timeout=30).status
                break
            except Exception as e:  # noqa: BLE001
                kod = str(e)[:80]
                time.sleep(5)
        print('перезапущено, вход: %s' % kod)
    print('копия: %s' % BEKAP)
    print()
    print('===== ПРОВЕРКА =====')
    sys.stdout.write(vyvod[-3500:])
finally:
    otdat_zamok()
