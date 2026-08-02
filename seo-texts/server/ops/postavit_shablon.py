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
ЦЕЛЬ = r'C:\seostat\app\templates'
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
    if not (источник and имя.endswith('.html')) or '..' in имя or '\\' in имя:
        print('нужно: postavit_shablon.py <файл-на-дропе> <шаблон.html>')
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

    было = проба('/obzvon/centro/')[0]
    shutil.copy2(ист, цель)
    print(f'записан {цель}: {os.path.getsize(цель)} байт')

    print('stop :', sh([NSSM, 'stop', 'obzvon']))
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
        беки = sorted(f for f in os.listdir(ЦЕЛЬ)
                      if f.startswith(имя + '.bak-'))
        if беки:
            shutil.copy2(os.path.join(ЦЕЛЬ, беки[-1]), цель)
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
