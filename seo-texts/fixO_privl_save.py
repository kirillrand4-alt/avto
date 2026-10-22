# -*- coding: utf-8 -*-
r"""fixO (22.10): починка статуса «Перевёл в привлечение» — сохранение давало «Некорректный результат звонка».

В fixM статус privlechenie добавлен в CALL_RESULT_CHOICES/LABELS (кнопка, вкладка, статистика), но валидатор
save_call проверяет результат по ОТДЕЛЬНОМУ набору CALL_RESULTS (services/centro_sales.py, строка 25) — туда
privlechenie не попал, поэтому нажатие кнопки у менеджера (Волков) падало с HTTP 422 «Некорректный результат
звонка». Из-за этого ни одна компания в «привлечение» ещё не переведена — правка только добавляет статус в набор.

    python3 zapusk_na_servere.py fixO_privl_save.py --suho
    python3 zapusk_na_servere.py fixO_privl_save.py --primenit
Откат: вернуть файл из C:\centro2\_bekap\fixO-<время>\ и перезапустить панель.
"""
import io
import os
import shutil
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
APP = os.path.join(KOREN, 'app')
PUT = '/obzvon-meyer'
PORT = 8016
ZAMOK = r'C:\centro2\_zamok.txt'
VREMYA = time.strftime('%Y%m%d-%H%M%S')
SREDA = dict(os.environ, PYTHONIOENCODING='utf-8')
FAJL = 'services/centro_sales.py'

STAROE = '    "v_rabote",\n    "ne_ponravilas",\n    "dubl",\n}\n'
NOVOE = '    "v_rabote",\n    "ne_ponravilas",\n    "dubl",\n    "privlechenie",\n}\n'


def vzyat_zamok():
    if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
        os.remove(ZAMOK)
    try:
        fd = os.open(ZAMOK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit('ЗАМОК ЗАНЯТ: ' + io.open(ZAMOK, encoding='utf-8').read())
    os.write(fd, ('fixO %s' % time.strftime('%H:%M:%S')).encode('utf-8'))
    os.close(fd)


def otdat_zamok():
    try:
        os.remove(ZAMOK)
    except OSError:
        pass


def ostanovit():
    p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
    for l in p.stdout.decode('cp866', 'replace').splitlines():
        if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
            subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
    time.sleep(2)


def zapustit():
    lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
    lg.write('\n===== перезапуск: fixO %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
    lg.flush()
    subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg,
                     stderr=subprocess.STDOUT, creationflags=0x00000008 | 0x00000200,
                     close_fds=True, env=SREDA)
    import urllib.request
    kod = ''
    for _ in range(12):
        time.sleep(5)
        try:
            kod = urllib.request.urlopen('http://127.0.0.1:%d%s/centro/login' % (PORT, PUT), timeout=30).status
            if kod == 200:
                break
        except Exception as e:  # noqa: BLE001
            kod = str(e)[:80]
    return kod


def main():
    primenit = '--primenit' in sys.argv
    put = os.path.join(APP, FAJL)
    t = io.open(put, encoding='utf-8').read()
    if '"privlechenie",\n}\n' in t:
        print('уже применено: privlechenie в CALL_RESULTS')
        return
    n = t.count(STAROE)
    print('вхождений заменяемого блока: %d' % n)
    if n != 1:
        raise SystemExit('ожидалось 1 вхождение, найдено %d — остановка' % n)
    if not primenit:
        print('СУХОЙ ПРОГОН: добавлю "privlechenie" в набор CALL_RESULTS')
        return
    vzyat_zamok()
    try:
        papka = os.path.join(KOREN, '_bekap', 'fixO-' + VREMYA)
        dst = os.path.join(papka, FAJL.replace('/', os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(put, dst)
        io.open(put, 'w', encoding='utf-8', newline='').write(t.replace(STAROE, NOVOE, 1))
        cp = subprocess.run([VENV, '-m', 'py_compile', put], capture_output=True, text=True)
        if cp.returncode != 0:
            raise SystemExit('py_compile упал:\n' + (cp.stderr or '')[:500])
        # проверка под venv: статус теперь в наборе
        proba = subprocess.run([VENV, '-c',
                                'import sys; sys.path.insert(0, r"%s"); '
                                'from app.services import centro_sales as c; '
                                'print("OK" if "privlechenie" in c.CALL_RESULTS else "НЕТ")' % KOREN],
                               capture_output=True, text=True, cwd=KOREN)
        print('privlechenie в CALL_RESULTS:', (proba.stdout or proba.stderr).strip()[-60:])
        ostanovit()
        kod = zapustit()
        print('ЗАПИСАНО; копия %s; перезапуск, локальный /centro/login = %s' % (papka, kod))
    finally:
        otdat_zamok()


if __name__ == '__main__':
    main()
