# -*- coding: utf-8 -*-
r"""fixKZ (21.10): панель КЦ – логин user3 становится вторым входом Журавлева (user2) в его очередь.

Владелец 21.10: «user1 – Кирчатов Никита Андреевич, user2 – Журавлев Александр Анатольевич; сделать, чтобы он мог заходить
под user2 и как user3», выбран вариант «тот же user2»: под любым из двух логинов – одна очередь user2, звонки и статистика
пишутся на user2. Компаний у user3 нет с утра (fixKR раздал их user1/user2), своих статусов у него не было.

Что меняет:
  * C:\seostat\app\api\routes_centro_sales.py – в login() после обычной проверки пароля вызывается _fixKZ_vhod_kak()
    (блок fixKZ в конце файла): логин ищется в таблице vhod_kak базы продаж ЭТОЙ панели, пароль сверяется с его
    bcrypt-хешем, сеанс выдаётся тому продавцу, на кого логин указывает. У p25 (8014, тот же код) таблицы нет – там
    ничего не меняется, и 8014 не перезапускается;
  * C:\seostat\data\centro_sales.db – таблица vhod_kak (user3 -> user2; хеш пароля копируется из users одной SQL-командой,
    открытый пароль скрипт не видит), user3 в users отключается (is_active=0): при раздаче новых компаний его больше нет,
    в списках продавцов тоже, старые сеансы user3 перестают действовать (вход заново – уже как user2).

Проверка до записи (--suho и --primenit): копии кода и баз в C:\seostat\_stage\fixKZ-<время>, код «до» и «после», на копиях
баз ставятся проверочные пароли (случайные, нигде не печатаются): вход user2 – как был; вход user3 – до правки пустая
очередь user3, после – очередь user2 (то же число компаний); неверный пароль – ошибка; старый сеанс user3 – на вход; p25 –
вход как до правки.

    python3 zapusk_na_servere.py fixKZ_vhod.py --suho
    python3 zapusk_na_servere.py fixKZ_vhod.py --primenit   # замок, копии, запись, py_compile, nssm restart obzvon, база
    python3 zapusk_na_servere.py fixKZ_vhod.py --otkat C:\seostat\_bekap\fixKZ-<время>
Откат (--otkat): routes_centro_sales.py из копии, `UPDATE users SET is_active=1 WHERE username='user3'`, nssm restart obzvon.
Таблица vhod_kak старому коду не мешает. Сменить пароль второго входа: centro_users.py set-password --username user3
(это снова включит user3), затем ещё раз fixKZ_vhod.py --primenit – он перенесёт новый хеш и снова отключит user3.
"""

KOD = r'''


# ===================================================================== fixKZ (21.10): второй логин продавца
# Владелец 21.10: user2 – Журавлев А. А., логин user3 должен входить «тем же user2». Второй логин живёт в таблице vhod_kak
# базы продаж ЭТОЙ панели: логин, bcrypt-хеш пароля и продавец, на которого он указывает. Сам user3 в users отключён, поэтому
# компаний при раздаче не получает и в списках продавцов не стоит. Вход по второму логину выдаёт сеанс того продавца:
# очередь, звонки, статистика – его. У p25 таблицы нет – там всё как раньше. Обычный вход проверяется первым.
import sqlite3 as _kz_sq


def _fixKZ_vhod_kak(login: str, password: str) -> dict | None:
    try:
        with sales.connect() as conn:
            r = conn.execute("SELECT password_hash, kak FROM vhod_kak WHERE login=?", (login,)).fetchone()
            if not r or not sales.verify_password(password, r["password_hash"]):
                return None
            u = conn.execute("SELECT * FROM users WHERE username=? AND is_active=1", (r["kak"],)).fetchone()
    except _kz_sq.OperationalError:     # таблицы vhod_kak нет (p25) – второго логина нет
        return None
    return dict(u) if u else None
# ===================================================================== /fixKZ
'''
YAKOR = '    user = sales.authenticate(username.strip(), password)\n'
NOVOE = '    user = sales.authenticate(username.strip(), password) or _fixKZ_vhod_kak(username.strip(), password)   # fixKZ\n'
PRIZNAK = '# ===================================================================== fixKZ (21.10): второй логин продавца'
LOGIN, KAK = 'user3', 'user2'

import hashlib
import io
import json
import os
import py_compile
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\seostat'
DATA = os.path.join(KOREN, 'data')
DROP = r'C:\seostat\drop\drop-storage'
ZAMOK = os.path.join(KOREN, '_zamok.txt')
T = time.strftime('%Y%m%d-%H%M%S')
STAGE = os.path.join(KOREN, '_stage', 'fixKZ-' + T)
BEKAP = os.path.join(KOREN, '_bekap', 'fixKZ-' + T)
RCS_REL = os.path.join('app', 'api', 'routes_centro_sales.py')
BAZY = {'kc': ('centro_sales.db', 'centrifugal.db'), 'p25': ('p25_sales.db', 'p25.db')}
PUT = {'kc': '/obzvon', 'p25': '/p25'}
log = []


def p(*a):
    s = ' '.join(str(x) for x in a)
    log.append(s)
    print(s, flush=True)


def sha(t):
    return hashlib.sha256(t.encode('utf-8')).hexdigest()[:16]


def chitat(put):
    return io.open(put, encoding='utf-8', newline='').read()


def pisat(put, t):
    with io.open(put, 'w', encoding='utf-8', newline='') as f:
        f.write(t)


def pravka_koda(koren) -> str:
    put = os.path.join(koren, RCS_REL)
    t = chitat(put)
    nl = '\r\n' if '\r\n' in t else '\n'          # файл на сервере в CRLF – правка в том же стиле строк
    yakor, novoe, kod = (x.replace('\n', nl) for x in (YAKOR, NOVOE, KOD))
    if PRIZNAK in t:
        if t.count(novoe) != 1:
            raise SystemExit('блок fixKZ есть, а строка входа не правлена – руками разобраться')
        return 'уже есть'
    if t.count(yakor) != 1:
        raise SystemExit('якорь входа найден %d раз' % t.count(yakor))
    pisat(put, t.replace(yakor, novoe) + kod)
    py_compile.compile(put, doraise=True)
    return 'вход: строка заменена, блок fixKZ дописан'


def migraciya(put_db) -> str:
    """user3 -> vhod_kak (хеш копируется SQL-ом, в Python не попадает), user3 отключается. Идемпотентно."""
    s = sqlite3.connect(put_db, timeout=30)
    try:
        s.execute('BEGIN IMMEDIATE')
        u3 = s.execute('SELECT is_active FROM users WHERE username=?', (LOGIN,)).fetchone()
        u2 = s.execute('SELECT is_active, role FROM users WHERE username=?', (KAK,)).fetchone()
        if not u3:
            raise SystemExit('нет пользователя %s' % LOGIN)
        if not u2 or u2[0] != 1 or u2[1] != 'sales':
            raise SystemExit('%s не активный продавец: %s' % (KAK, u2))
        naz = s.execute('SELECT COUNT(*) FROM company_assignment WHERE username=?', (LOGIN,)).fetchone()[0]
        if naz:
            raise SystemExit('у %s есть назначения (%d) – после отключения они пропадут из виду; стоп' % (LOGIN, naz))
        s.execute('CREATE TABLE IF NOT EXISTS vhod_kak (login TEXT PRIMARY KEY, password_hash TEXT NOT NULL, '
                  'kak TEXT NOT NULL, sozdano TEXT, primechanie TEXT)')
        if u3[0] == 1:      # активный user3 – свежий хеш (в т.ч. после смены пароля) переносится; неактивный – уже перенесён
            s.execute('INSERT OR REPLACE INTO vhod_kak(login, password_hash, kak, sozdano, primechanie) '
                      'SELECT username, password_hash, ?, ?, ? FROM users WHERE username=?',
                      (KAK, time.strftime('%Y-%m-%dT%H:%M:%S'), 'fixKZ 21.10: второй вход Журавлева А. А. в очередь user2', LOGIN))
            s.execute("UPDATE users SET is_active=0, updated_at=? WHERE username=?",
                      (time.strftime('%Y-%m-%dT%H:%M:%S+03:00'), LOGIN))
        s.execute('COMMIT')
        return 'vhod_kak: %s; %s is_active=%s' % (
            s.execute('SELECT login, kak FROM vhod_kak').fetchall(), LOGIN,
            s.execute('SELECT is_active FROM users WHERE username=?', (LOGIN,)).fetchone()[0])
    except BaseException:
        if s.in_transaction:
            s.execute('ROLLBACK')
        raise
    finally:
        s.close()


def kopiya_bazy(src, dst):
    a = sqlite3.connect('file:%s?mode=ro' % src, uri=True, timeout=30)
    b = sqlite3.connect(dst)
    a.backup(b)
    b.close()
    a.close()


# ---------------------------------------------------------------- проверка в отдельном процессе (venv)
def proverka(var_koren, konf, migr, vyhod):
    sys.path.insert(0, var_koren)
    os.chdir(var_koren)
    import logging
    logging.disable(logging.CRITICAL)
    from fastapi.testclient import TestClient
    from app.obzvon import create_app
    from app.api import routes_centro_sales as rcs
    from app.services import centro_sales as sales
    db = os.environ['CENTRO_SALES_DB']
    s = sqlite3.connect(db)
    prod = [r[0] for r in s.execute("SELECT username FROM users WHERE role='sales' AND is_active=1 ORDER BY username")]
    parol = {}
    for u in ((KAK, LOGIN) if konf == 'kc' else prod[:1]):
        parol[u] = secrets.token_urlsafe(18)      # проверочный пароль только на копии базы, нигде не печатается
        s.execute('UPDATE users SET password_hash=? WHERE username=?', (sales.password_hash(parol[u]), u))
    s.commit()
    s.close()
    res = {'est_fixKZ': hasattr(rcs, '_fixKZ_vhod_kak')}
    if migr:
        res['migraciya'] = migraciya(db)
    vn = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    bp = PUT[konf]

    def vhod(login, pw):
        k = TestClient(vn, follow_redirects=False)
        r = k.post(bp + '/centro/login', data={'username': login, 'password': pw})
        out = {'login': r.status_code, 'kuda': r.headers.get('location', '').replace(bp, '')}
        if 'centro_session' in r.headers.get('set-cookie', ''):
            g = k.get(bp + '/centro')
            m = re.search(r'class="total-count">(\d+) компаний', g.text)
            u = re.search(r'<div class="user-block">\s*<span>([^<·]+)·', g.text)
            out.update(glavnaya=g.status_code, kompaniy=int(m.group(1)) if m else None, kto=u.group(1).strip() if u else None)
        return out

    for u, pw in parol.items():
        res['%s верный' % u] = vhod(u, pw)
        res['%s неверный' % u] = vhod(u, pw + 'x')
    if konf == 'kc':
        k = TestClient(vn, follow_redirects=False)
        k.cookies.set('centro_session', rcs._token(LOGIN, int(time.time()) + 3600))
        r = k.get(bp + '/centro')
        res['старый сеанс user3'] = [r.status_code, r.headers.get('location', '').replace(bp, '')]
        res['второй логин чужим паролем'] = vhod(LOGIN, parol[KAK])
    io.open(vyhod, 'w', encoding='utf-8').write(json.dumps(res, ensure_ascii=False))


def stadiya() -> bool:
    os.makedirs(os.path.join(STAGE, 'db'), exist_ok=True)
    ign = shutil.ignore_patterns('__pycache__', '*.pyc')
    do_k, posle_k = os.path.join(STAGE, 'do'), os.path.join(STAGE, 'posle')
    shutil.copytree(os.path.join(KOREN, 'app'), os.path.join(do_k, 'app'), ignore=ign)
    shutil.copytree(os.path.join(do_k, 'app'), os.path.join(posle_k, 'app'))
    p('правка в stage:', pravka_koda(posle_k))
    procy = []
    for konf, (sdb, kdb) in BAZY.items():
        kat = os.path.join(STAGE, 'db', '%s-kat.db' % konf)
        kopiya_bazy(os.path.join(DATA, kdb), kat)
        for imya, k in (('do', do_k), ('posle', posle_k)):
            sd = os.path.join(STAGE, 'db', '%s-sales-%s.db' % (konf, imya))
            kopiya_bazy(os.path.join(DATA, sdb), sd)
            env = {x: v for x, v in os.environ.items() if not x.startswith(('CENTRO', 'PARK_', 'OBZVON', 'CENTRIFUGAL'))}
            env.update(PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=k, OBZVON_ROOT_PATH=PUT[konf],
                       CENTRO_SALES_DB=sd, CENTRIFUGAL_DB=kat, CENTRO_DB=kat, PARK_OCHERED_SALES_DB=sd, PARK_OCHERED_DB=kat,
                       PARK_PANEL_DB=os.path.join(STAGE, 'db', 'net-park.db'), CENTRO_SESSION_SECRET='x' * 40)
            vyh = os.path.join(STAGE, '%s-%s.json' % (konf, imya))
            migr = '1' if (konf == 'kc' and imya == 'posle') else '0'
            procy.append((konf, imya, vyh, subprocess.Popen(
                [VENV, os.path.abspath(__file__), '--proverka', k, konf, migr, vyh], cwd=k, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)))
    rez = {}
    for konf, imya, vyh, pr in procy:
        out = pr.communicate(timeout=900)[0].decode('utf-8', 'replace')
        if pr.returncode or not os.path.exists(vyh):
            p('ПРОВЕРКА %s/%s УПАЛА rc=%s:\n%s' % (konf, imya, pr.returncode, out[-2500:]))
            return False
        rez[(konf, imya)] = json.load(io.open(vyh, encoding='utf-8'))
        p('%s/%s: %s' % (konf, imya, json.dumps(rez[(konf, imya)], ensure_ascii=False)))
    plokh = []
    do, po = rez[('kc', 'do')], rez[('kc', 'posle')]
    u2 = do.get('%s верный' % KAK, {})
    if not (u2.get('login') == 303 and u2.get('glavnaya') == 200 and u2.get('kto') == KAK):
        plokh.append('до: вход %s не работает: %s' % (KAK, u2))
    if po.get('%s верный' % KAK) != u2:
        plokh.append('вход %s изменился: %s -> %s' % (KAK, u2, po.get('%s верный' % KAK)))
    v3 = po.get('%s верный' % LOGIN, {})
    if not (v3.get('login') == 303 and v3.get('glavnaya') == 200 and v3.get('kto') == KAK and v3.get('kompaniy') == u2.get('kompaniy')):
        plokh.append('после: вход %s не дал очередь %s: %s (у %s %s)' % (LOGIN, KAK, v3, KAK, u2.get('kompaniy')))
    for u in (KAK, LOGIN):
        if po.get('%s неверный' % u, {}).get('kuda') != '/centro/login?error=1':
            plokh.append('неверный пароль %s: %s' % (u, po.get('%s неверный' % u)))
    if po.get('старый сеанс user3', [0])[0] != 303:
        plokh.append('старый сеанс user3 после: %s (ждём 303 на вход)' % po.get('старый сеанс user3'))
    if po.get('второй логин чужим паролем', {}).get('kuda') != '/centro/login?error=1':
        plokh.append('user3 с паролем user2 пустил: %s' % po.get('второй логин чужим паролем'))
    p25d, p25p = rez[('p25', 'do')], rez[('p25', 'posle')]
    if {k: v for k, v in p25d.items() if k != 'est_fixKZ'} != {k: v for k, v in p25p.items() if k != 'est_fixKZ'}:
        plokh.append('p25 изменился: %s -> %s' % (p25d, p25p))
    for x in plokh:
        p('ПЛОХО: ' + x)
    p('ПЛОХИХ ПРОВЕРОК: %d' % len(plokh))
    return not plokh


class BezRedirekta(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


urllib.request.install_opener(urllib.request.build_opener(BezRedirekta))


def http(port, url):
    try:
        r = urllib.request.urlopen('http://127.0.0.1:%d%s' % (port, url), timeout=30)
        return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:  # noqa: BLE001
        return str(e)[:60]


ZHIVYE = [(8012, '/obzvon/centro/login'), (8012, '/obzvon/centro'), (8014, '/p25/centro/login'), (8011, '/')]


def nssm_restart(svc):
    for exe in (r'C:\Windows\System32\nssm.exe', r'C:\nssm.exe'):
        if os.path.exists(exe):
            r = subprocess.run([exe, 'restart', svc], capture_output=True, timeout=120)
            return (r.stdout + r.stderr).decode('utf-16-le' if b'\x00' in r.stdout + r.stderr else 'cp866', 'replace').replace('\x00', '').strip()
    return 'nssm не найден'


def zhdat_vhod():
    for _ in range(30):
        time.sleep(2)
        if http(8012, '/obzvon/centro/login') == 200:
            return 200
    return http(8012, '/obzvon/centro/login')


def vzyat_zamok():
    if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
        os.remove(ZAMOK)
    try:
        fd = os.open(ZAMOK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print('ЗАМОК ЗАНЯТ: ' + io.open(ZAMOK, encoding='utf-8').read())
        raise SystemExit(3)
    os.write(fd, ('fixKZ (второй вход user3 -> user2) %s' % time.strftime('%H:%M:%S')).encode('utf-8'))
    os.close(fd)


def otkat(papka):
    vzyat_zamok()
    try:
        shutil.copy2(os.path.join(papka, RCS_REL), os.path.join(KOREN, RCS_REL))
        p('код возвращён из', papka)
        s = sqlite3.connect(os.path.join(DATA, 'centro_sales.db'), timeout=30)
        s.execute("UPDATE users SET is_active=1 WHERE username=?", (LOGIN,))
        s.commit()
        s.close()
        p('user3 включён обратно')
        p('перезапуск obzvon:', nssm_restart('obzvon'), zhdat_vhod())
    finally:
        os.remove(ZAMOK)


def main():
    rezhim = sys.argv[1] if len(sys.argv) > 1 else '--suho'
    if rezhim == '--proverka':
        return proverka(sys.argv[2], sys.argv[3], sys.argv[4] == '1', sys.argv[5])
    if rezhim == '--otkat':
        return otkat(sys.argv[2])
    p('fixKZ %s, %s' % (rezhim, T))
    zamok = rezhim == '--primenit'
    if zamok:
        vzyat_zamok()
    zapisano = migr = False
    try:
        do_zh = {'%d %s' % k: http(*k) for k in ZHIVYE}
        p('живые до:', do_zh)
        ok = stadiya()
        if rezhim != '--primenit':
            p('сухой прогон: живые файлы и база не трогались')
            return
        if not ok:
            p('ПРОВЕРКА НЕ ПРОШЛА – живые файлы не трогались')
            raise SystemExit(1)
        os.makedirs(os.path.join(BEKAP, 'app', 'api'), exist_ok=True)
        shutil.copy2(os.path.join(KOREN, RCS_REL), os.path.join(BEKAP, RCS_REL))
        if sha(chitat(os.path.join(KOREN, RCS_REL))) != sha(chitat(os.path.join(STAGE, 'do', RCS_REL))):
            p('ЖИВОЙ ФАЙЛ ИЗМЕНИЛСЯ ПОСЛЕ КОПИИ В STAGE – запись отменена')
            raise SystemExit(1)
        kopiya_bazy(os.path.join(DATA, 'centro_sales.db'), os.path.join(BEKAP, 'centro_sales.db'))
        p('копии прежних: код и база ->', BEKAP)
        zapisano = True
        p('код:', pravka_koda(KOREN))
        if sha(chitat(os.path.join(KOREN, RCS_REL))) != sha(chitat(os.path.join(STAGE, 'posle', RCS_REL))):
            raise RuntimeError('живой файл не совпал с проверенным stage')
        p('перезапуск obzvon (8012):', nssm_restart('obzvon'), zhdat_vhod())
        migr = True
        p('база:', migraciya(os.path.join(DATA, 'centro_sales.db')))
        posle = {'%d %s' % k: http(*k) for k in ZHIVYE}
        p('живые после:', posle)
        if posle != do_zh:
            raise RuntimeError('коды ответов изменились: %s -> %s' % (do_zh, posle))
        p('ГОТОВО')
    except Exception as e:  # noqa: BLE001 – после записи любая ошибка (в т.ч. py_compile) = откат
        if not zapisano:
            raise
        p('ОШИБКА ПОСЛЕ ЗАПИСИ: %s – откат' % e)
        shutil.copy2(os.path.join(BEKAP, RCS_REL), os.path.join(KOREN, RCS_REL))
        if migr:
            s = sqlite3.connect(os.path.join(DATA, 'centro_sales.db'), timeout=30)
            s.execute("UPDATE users SET is_active=1 WHERE username=?", (LOGIN,))
            s.commit()
            s.close()
        p('перезапуск obzvon после отката:', nssm_restart('obzvon'), zhdat_vhod())
        raise SystemExit(1)
    finally:
        if zamok:
            try:
                os.remove(ZAMOK)
            except OSError:
                pass
        io.open(os.path.join(DROP, 'fixKZ-%s-%s.txt' % (rezhim.strip('-'), T)), 'w', encoding='utf-8').write('\n'.join(log))
        shutil.rmtree(os.path.join(STAGE, 'db'), ignore_errors=True)     # копии баз не копим
        if 'ГОТОВО' in log[-1:] or rezhim != '--primenit':
            shutil.rmtree(STAGE, ignore_errors=True)


if __name__ == '__main__':
    main()
