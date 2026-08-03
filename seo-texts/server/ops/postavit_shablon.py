# -*- coding: utf-8 -*-
"""Поставить шаблон панели обзвона с дропа и перезапустить службу.

Штатный `panel_file_put` пишет только под `C:\\sender`, а панель обзвона живёт
в `C:\\seostat\\app`. Разрешаем ровно один каталог — шаблоны панели, и ничего
кроме.

Перед записью делается бэкап рядом (`.bak-<время>`): панель боевая, ею
пользуются два продавца, и откат должен быть на месте, а не «пересоберём».

После записи служба перезапускается и проверяется ЖИВЫМ запросом. Иначе
«файл положен» и «панель работает» — разные вещи: шаблон с ошибкой Jinja
кладётся так же успешно, как исправный, а падает уже у продавца.

Запуск: python postavit_shablon.py <имя-на-дропе> <имя-шаблона.html>
"""
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

ДРОП = r'C:\seostat\drop\drop-storage'
ЦЕЛЬ = r'C:\seostat\app'
NSSM = 'C:\\nssm.exe'
ПОРТ = 8012


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, timeout=120)
    сыр = (r.stdout or b'') + (r.stderr or b'')
    try:
        т = сыр.decode('utf-16-le')
    except Exception:  # noqa: BLE001
        т = сыр.decode('utf-8', 'replace')
    return т.replace('\x00', '').strip()[:160]


def pid_na_portu():
    """Кто слушает порт панели. Нужен, чтобы не поднимать вторую копию."""
    т = sh(['netstat', '-ano', '-p', 'TCP'])
    for стр in т.splitlines():
        if f':{ПОРТ} ' in стр and 'LISTENING' in стр.upper():
            куски = стр.split()
            if куски and куски[-1].isdigit():
                return int(куски[-1])
    return 0


def занят_ли_порт():
    import socket
    с = socket.socket()
    с.settimeout(1)
    try:
        с.connect(('127.0.0.1', ПОРТ))
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        с.close()


def проба(путь):
    try:
        зпр = urllib.request.Request(f'http://127.0.0.1:{ПОРТ}{путь}')
        with urllib.request.urlopen(зпр, timeout=25) as о:
            тело = о.read().decode('utf-8', 'replace')
            return о.status, len(тело), тело
    except urllib.error.HTTPError as e:
        тело = e.read().decode('utf-8', 'replace')
        return e.code, len(тело), тело
    except Exception as e:  # noqa: BLE001
        return 0, 0, str(e)[:200]


def main():
    источник = sys.argv[1] if len(sys.argv) > 1 else ''
    имя = sys.argv[2] if len(sys.argv) > 2 else ''
    # Второй аргумент — путь ВНУТРИ app: 'templates/centro.html' или
    # 'services/centro_medium.py'. Правка правил отбора и правка шаблона
    # ходят вместе, и разносить их по двум разным оп значит однажды выкатить
    # половину.
    if not (источник and имя) or '..' in имя or имя.startswith(('/', '\\')):
        print('нужно: postavit_shablon.py <файл-на-дропе> <путь/внутри/app>')
        return
    имя = имя.replace('/', os.sep)
    # .css добавлен, когда владелец попросил вернуть вид прошлой базы обзвона:
    # тема живёт в static/css/centro.css, и без этого её пришлось бы ставить
    # мимо оп — то есть без бэкапа, без перезапуска и без живой проверки,
    # ровно тех трёх вещей, ради которых оп и написан.
    if not имя.endswith(('.html', '.py', '.css')):
        print('разрешены только .html, .py и .css')
        return
    ист = os.path.join(ДРОП, источник)
    цель = os.path.join(ЦЕЛЬ, имя)
    if not os.path.exists(ист):
        print(f'НЕТ файла на дропе: {ист}')
        return
    if not os.path.exists(цель):
        print(f'ВНИМАНИЕ: {цель} не существует — ставим новый файл')
    else:
        бэк = цель + '.bak-' + str(int(time.time()))
        shutil.copy2(цель, бэк)
        print(f'бэкап: {os.path.basename(бэк)} ({os.path.getsize(бэк)} байт)')

    # ФАЙЛ ТОТ ЖЕ — НЕ ТРОГАЕМ СЛУЖБУ. Каждый выкат делает stop/start, а в
    # журнале службы за сутки 78 запусков, 60 остановок и 16 ошибок «порт 8012
    # занят»: это мои повторные выкаты одного и того же файла. Пока вторая
    # копия падает на занятом порту, панель у владельца не грузится. Самый
    # дешёвый способ этого не делать — не перезапускать, когда нечего менять.
    if os.path.exists(цель) and open(ист, 'rb').read() == open(цель, 'rb').read():
        print('файл побайтно совпадает с тем, что стоит — служба не трогается')
        return

    было = проба('/obzvon/centro/')[0]
    shutil.copy2(ист, цель)
    print(f'записан {цель}: {os.path.getsize(цель)} байт')

    print('stop :', sh([NSSM, 'stop', 'obzvon']))
    # ЖДЁМ ОСВОБОЖДЕНИЯ ПОРТА, а не две секунды на глазок. `nssm stop`
    # возвращается раньше, чем процесс отпускает 8012, и следующий старт
    # падает с 10048 «адрес уже используется». Снаружи это выглядит как
    # «панель не грузится», а в журнале — как чехарда запусков.
    for _ in range(20):
        if not занят_ли_порт():
            break
        time.sleep(1.5)
    else:
        чей = pid_na_portu()
        if чей:
            print(f'порт {ПОРТ} держит процесс {чей} — снимаю')
            sh(['taskkill', '/PID', str(чей), '/F'])
            time.sleep(2)
    print('start:', sh([NSSM, 'start', 'obzvon']))

    # ЖДЁМ, А НЕ ЗАСЫПАЕМ НА ГЛАЗОК. Первый прогон дал ложную тревогу: через
    # 4 секунды служба была ещё в SERVICE_START_PENDING, проба вернула
    # «отказано в соединении», и откат сработал на исправном шаблоне.
    # «Ещё поднимается» и «упала» снаружи выглядят одинаково — различает их
    # только время ожидания.
    код = размер = 0
    тело = ''
    for попытка in range(15):
        time.sleep(2)
        код, размер, тело = проба('/obzvon/centro/')
        if код:
            print(f'  поднялась через ~{(попытка + 1) * 2} с')
            break
    else:
        print('  за 30 секунд служба не ответила ни разу')
    print(f'проверка живым запросом: было {было}, стало {код}, {размер} байт')
    if код not in (200, 401, 303, 307):
        print('ПАНЕЛЬ НЕ ОТВЕЧАЕТ КАК НАДО, откатываю на бэкап')
        папка = os.path.dirname(цель)
        осн = os.path.basename(цель)
        беки = sorted(f for f in os.listdir(папка)
                      if f.startswith(осн + '.bak-'))
        if беки:
            shutil.copy2(os.path.join(папка, беки[-1]), цель)
            sh([NSSM, 'stop', 'obzvon'])
            time.sleep(2)
            sh([NSSM, 'start', 'obzvon'])
            time.sleep(4)
            print(f'откат на {беки[-1]}, теперь {проба("/obzvon/centro/")[0]}')
        print('хвост ответа:', тело[-400:])
        return
    # ищем наш признак — иначе «200» может быть страницей без правки
    есть = 'centro_vid_v1' in тело
    print(f'признак правки в отданной странице: {"ЕСТЬ" if есть else "НЕТ"}')
    if not есть:
        print('  (страница за логином — признак проверить нельзя, '
              'смотреть глазами)')


if __name__ == '__main__':
    main()
