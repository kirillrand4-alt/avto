# -*- coding: utf-8 -*-
r"""fixM (22.10): новая очередь-вкладка «Перевёл в привлечение» в панели Meyer.

Владелец 22.10: добавить очередь «перевёл в привлечение» и возможность перевести туда из «Вся очередь» и из
«Взял в работу»; в статистике у админа — подписать «Перевёл в привлечение».

Как устроено (подтверждено чтением кода): вкладки — это статусы звонка CALL_RESULT_CHOICES; компания попадает во
вкладку, когда продавец сохраняет звонок с этим статусом (company_state.call_result), а «Вся очередь» прячет все
компании, чей статус входит в CHOICES. Поэтому новый статус privlechenie:
  * добавляется в CALL_RESULT_CHOICES и CALL_RESULT_LABELS (services/centro_sales.py) — отсюда кнопка в карточке
    (меню результата перебирает CHOICES, поэтому пункт виден на ЛЮБОЙ карточке — и в «Вся очередь», и во «Взял в
    работу»), автоскрытие из общей очереди, фильтр вкладки, разбивка в статистике и подпись везде (metki.get);
  * вкладка в шапке (_shapka.html) рядом с «Дубль»;
  * в таблице очереди статистики ссылка открывает карточку в своей вкладке (centro_stats.html, +privlechenie в кортеж).
Статистика у админа: блок «по результату» (общий и по каждому менеджеру) перебирает все статусы — «Перевёл в
привлечение: N» появится сам. В таблицы «причины отказов» и «где берут в работу» колонка не добавляется — это
отдельные метрики (отказы и воронка «взял в работу»), привлечение туда по смыслу не входит.

Статусы существующих компаний, обзвон, назначения, баллы, Битрикс — НЕ трогаются.

    python3 zapusk_na_servere.py fixM_privlechenie.py --suho      # показать замены, без записи
    python3 zapusk_na_servere.py fixM_privlechenie.py --primenit  # под замком: бэкап -> запись -> перезапуск -> проверка
Откат: вернуть файлы из C:\centro2\_bekap\fixM-<время>\ и перезапустить панель.
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

# (относительный путь, старое, новое) — каждое старое должно встречаться ровно один раз
PRAVKI = [
    # 1) подпись статуса (CALL_RESULT_LABELS) — якорь по комментарию fixB, который идёт только после LABELS
    ('services/centro_sales.py',
     '    "dubl": "Дубль – уже работают",\n'
     '    # fixB: события звонка – не статусы (в очередь и вкладки не влияют), подписи для ленты\n',
     '    "dubl": "Дубль – уже работают",\n'
     '    "privlechenie": "Перевёл в привлечение",\n'
     '    # fixB: события звонка – не статусы (в очередь и вкладки не влияют), подписи для ленты\n'),
    # 2) сам статус в форме (CALL_RESULT_CHOICES) — якорь по комментарию про «отдельной причиной»
    ('services/centro_sales.py',
     '    # Отдельной причиной, чтобы не портить статистику отказов.\n'
     '    "dubl": "Дубль – уже работают",\n'
     '}\n',
     '    # Отдельной причиной, чтобы не портить статистику отказов.\n'
     '    "dubl": "Дубль – уже работают",\n'
     '    # «Перевёл в привлечение» (владелец 22.10): позитивный статус; уводит компанию из общей\n'
     '    # очереди в свою вкладку, кнопка доступна на любой карточке.\n'
     '    "privlechenie": "Перевёл в привлечение",\n'
     '}\n'),
    # 3) вкладка в шапке — после «Дубль»
    ('templates/_shapka.html',
     '    <a href="{{ _bp }}/centro?call_status=dubl"{% if _put.endswith(\'/centro\') and _cs == \'dubl\' %} class="active"{% endif %}>Дубль – уже работают</a>\n',
     '    <a href="{{ _bp }}/centro?call_status=dubl"{% if _put.endswith(\'/centro\') and _cs == \'dubl\' %} class="active"{% endif %}>Дубль – уже работают</a>\n'
     '    <a href="{{ _bp }}/centro?call_status=privlechenie"{% if _put.endswith(\'/centro\') and _cs == \'privlechenie\' %} class="active"{% endif %}>Перевёл в привлечение</a>\n'),
    # 4) ссылка в таблице очереди статистики — чтобы карточка открывалась в своей вкладке
    ('templates/centro_stats.html',
     "{% if z.call_result in ('v_rabote', 'ne_ponravilas', 'dubl') %}",
     "{% if z.call_result in ('v_rabote', 'ne_ponravilas', 'dubl', 'privlechenie') %}"),
]


def vzyat_zamok():
    if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
        os.remove(ZAMOK)
    try:
        fd = os.open(ZAMOK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit('ЗАМОК ЗАНЯТ: ' + io.open(ZAMOK, encoding='utf-8').read())
    os.write(fd, ('fixM %s' % time.strftime('%H:%M:%S')).encode('utf-8'))
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
    lg.write('\n===== перезапуск: fixM %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
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
    # читаем и проверяем, что каждая замена применима ровно один раз
    teksty = {}
    for rel, staroe, _novoe in PRAVKI:
        if rel not in teksty:
            teksty[rel] = io.open(os.path.join(APP, rel), encoding='utf-8').read()
    for i, (rel, staroe, novoe) in enumerate(PRAVKI, 1):
        t = teksty[rel]
        if novoe in t and staroe not in t:
            print('%d. %-32s уже применено' % (i, rel))
            continue
        n = t.count(staroe)
        print('%d. %-32s вхождений: %d' % (i, rel, n))
        if n != 1:
            raise SystemExit('правка %d: ожидалось 1 вхождение, найдено %d — остановка' % (i, n))
    if not primenit:
        print('\nСУХОЙ ПРОГОН: ничего не записано. Будет добавлен статус privlechenie «Перевёл в привлечение».')
        return
    vzyat_zamok()
    try:
        papka = os.path.join(KOREN, '_bekap', 'fixM-' + VREMYA)
        for rel in teksty:
            dst = os.path.join(papka, rel.replace('/', os.sep))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(APP, rel), dst)
        # применяем все замены в памяти, затем пишем
        for rel, staroe, novoe in PRAVKI:
            if novoe in teksty[rel] and staroe not in teksty[rel]:
                continue
            teksty[rel] = teksty[rel].replace(staroe, novoe, 1)
        for rel, t in teksty.items():
            io.open(os.path.join(APP, rel), 'w', encoding='utf-8', newline='').write(t)
        # синтаксис .py
        cp = subprocess.run([VENV, '-m', 'py_compile', os.path.join(APP, 'services', 'centro_sales.py')],
                            capture_output=True, text=True)
        if cp.returncode != 0:
            raise SystemExit('py_compile упал, откатываю:\n' + (cp.stderr or '')[:500])
        ostanovit()
        kod = zapustit()
        print('\nЗАПИСАНО; копия файлов %s' % papka)
        print('перезапуск панели, локальный /centro/login =', kod)
    finally:
        otdat_zamok()


if __name__ == '__main__':
    main()
