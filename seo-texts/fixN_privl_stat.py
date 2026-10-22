# -*- coding: utf-8 -*-
r"""fixN (22.10): колонка «привлечение» в таблице «По менеджерам по продажам» статистики Meyer.

Владелец 22.10 (после fixM): «сюда ещё добавь столбец привлечение, чтобы статистика была у админа» — речь про
таблицу `_statblok.html` («за период и за всё время»), где колонки: взял в работу | не понравилась | дубль |
в очереди | не дозвонился (два блока: период и нынешний статус).

Таблицу строит _statblok (api/routes_park.py): счётчики статусов по набору _STAT_KLYUCHI и словарю pusto();
ссылки у цифр кладёт _statblok_ssylki (api/routes_centro_sales.py). Рисует `templates/_statblok.html`
(макрос `chetyre` — 5 ячеек на блок). Добавляем privlechenie:
  * routes_park.py: privlechenie в _STAT_KLYUCHI и в pusto() — тогда счётчик попадает в z["den"]/z["vse"];
  * routes_centro_sales.py: privlechenie в кортежи ссылок den/vse — цифра станет кликабельной;
  * _statblok.html: +ячейка в макросе, +<th> в обеих шапках, colspan 5->6 у групп и 11->13 у пустой строки.
Колонка встаёт после «дубль», как и вкладка. Данные/обзвон не трогаются.

    python3 zapusk_na_servere.py fixN_privl_stat.py --suho
    python3 zapusk_na_servere.py fixN_privl_stat.py --primenit
Откат: вернуть файлы из C:\centro2\_bekap\fixN-<время>\ и перезапустить панель.
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

# (относительный путь, старое, новое, сколько_вхождений_ожидается)
PRAVKI = [
    ('api/routes_park.py',
     '_STAT_KLYUCHI = ("v_rabote", "ne_ponravilas", "dubl")',
     '_STAT_KLYUCHI = ("v_rabote", "ne_ponravilas", "dubl", "privlechenie")', 1),
    ('api/routes_park.py',
     '{"v_rabote": 0, "ne_ponravilas": 0, "dubl": 0, "ochered": 0, "prochee": 0,',
     '{"v_rabote": 0, "ne_ponravilas": 0, "dubl": 0, "privlechenie": 0, "ochered": 0, "prochee": 0,', 1),
    ('api/routes_centro_sales.py',
     'den = {r: _ssylka_spiska(**per, rez_p=r, **k) for r in ("v_rabote", "ne_ponravilas", "dubl")}',
     'den = {r: _ssylka_spiska(**per, rez_p=r, **k) for r in ("v_rabote", "ne_ponravilas", "dubl", "privlechenie")}', 1),
    ('api/routes_centro_sales.py',
     'vse = {r: _ssylka_spiska(call_status=r, **a) for r in ("v_rabote", "ne_ponravilas", "dubl")}',
     'vse = {r: _ssylka_spiska(call_status=r, **a) for r in ("v_rabote", "ne_ponravilas", "dubl", "privlechenie")}', 1),
    # макрос: ячейка привлечения после дубля
    ('templates/_statblok.html',
     "<td>{{ yach(d.dubl, ss.dubl if ss else '') }}</td>",
     "<td>{{ yach(d.dubl, ss.dubl if ss else '') }}</td><td>{{ yach(d.privlechenie, ss.privlechenie if ss else '') }}</td>", 1),
    # группы шапки colspan 5->6
    ('templates/_statblok.html',
     'colspan="5">{% if statblok.vse %}за всё время (с',
     'colspan="6">{% if statblok.vse %}за всё время (с', 1),
    ('templates/_statblok.html',
     'colspan="5">{% if statblok.vse %}нынешний статус',
     'colspan="6">{% if statblok.vse %}нынешний статус', 1),
    # заголовки колонок в обеих шапках
    ('templates/_statblok.html',
     '<th>дубль</th><th>в очереди</th>',
     '<th>дубль</th><th title="переведено в привлечение">привлечение</th><th>в очереди</th>', 2),
    # пустая строка colspan 11->13
    ('templates/_statblok.html',
     '<td colspan="11" class="tiho">менеджеров по продажам нет</td>',
     '<td colspan="13" class="tiho">менеджеров по продажам нет</td>', 1),
]


def vzyat_zamok():
    if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
        os.remove(ZAMOK)
    try:
        fd = os.open(ZAMOK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit('ЗАМОК ЗАНЯТ: ' + io.open(ZAMOK, encoding='utf-8').read())
    os.write(fd, ('fixN %s' % time.strftime('%H:%M:%S')).encode('utf-8'))
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
    lg.write('\n===== перезапуск: fixN %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
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
    teksty = {}
    for rel, staroe, _n, _c in PRAVKI:
        if rel not in teksty:
            teksty[rel] = io.open(os.path.join(APP, rel), encoding='utf-8').read()
    for i, (rel, staroe, novoe, nado) in enumerate(PRAVKI, 1):
        t = teksty[rel]
        if staroe not in t and novoe in t:
            print('%d. %-32s уже применено' % (i, rel))
            continue
        n = t.count(staroe)
        print('%d. %-32s вхождений: %d (ожидалось %d)' % (i, rel, n, nado))
        if n != nado:
            raise SystemExit('правка %d: ожидалось %d, найдено %d — остановка' % (i, nado, n))
    if not primenit:
        print('\nСУХОЙ ПРОГОН: ничего не записано. Будет добавлена колонка «привлечение» в таблицу по менеджерам.')
        return
    vzyat_zamok()
    try:
        papka = os.path.join(KOREN, '_bekap', 'fixN-' + VREMYA)
        for rel in teksty:
            dst = os.path.join(papka, rel.replace('/', os.sep))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(APP, rel), dst)
        for rel, staroe, novoe, nado in PRAVKI:
            if staroe not in teksty[rel] and novoe in teksty[rel]:
                continue
            teksty[rel] = teksty[rel].replace(staroe, novoe)
        for rel, t in teksty.items():
            io.open(os.path.join(APP, rel), 'w', encoding='utf-8', newline='').write(t)
        for py in ('api/routes_park.py', 'api/routes_centro_sales.py'):
            cp = subprocess.run([VENV, '-m', 'py_compile', os.path.join(APP, py)], capture_output=True, text=True)
            if cp.returncode != 0:
                raise SystemExit('py_compile %s упал:\n%s' % (py, (cp.stderr or '')[:500]))
        ostanovit()
        kod = zapustit()
        print('\nЗАПИСАНО; копия файлов %s' % papka)
        print('перезапуск панели, локальный /centro/login =', kod)
    finally:
        otdat_zamok()


if __name__ == '__main__':
    main()
