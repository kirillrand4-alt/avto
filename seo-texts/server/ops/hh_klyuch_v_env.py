# -*- coding: utf-8 -*-
"""Положить ключи приложения hh в окружение панели, не проводя их через задание.

Пункт 9 владельца: «у меня появилось приложение hh, скажите куда положить с
какой переменной». Ответ: `C:\\sender\\panel.env`, переменные `HH_CLIENT_ID` и
`HH_CLIENT_SECRET` — именно их читает `ops/hh_bez_tehlpr.py`, и раннер
подкладывает `panel.env` в окружение каждого скрипта.

ПОЧЕМУ ОТДЕЛЬНЫЙ ОП, А НЕ ШТАТНЫЙ `panel_env_set`. Тот принимает значения
прямо в задании, а задание раннера — это файл на общем дропе. Секрет полежал
бы там открытым текстом. Здесь секрет вообще никуда не едет: скрипт читает его
на сервере из `VSEM-SESSIYAM.txt`, где владелец его и написал, и пишет рядом,
в `panel.env`. В вывод печатаются только ИМЕНА переменных и длины значений.

В git этот файл не попадёт: он читает, а не хранит.

Запуск: python hh_klyuch_v_env.py [--apply]
"""
import os
import re
import shutil
import sys
import time

ЗАДАНИЕ = r'C:\seostat\drop\drop-storage\VSEM-SESSIYAM.txt'
ENV = r'C:\sender\panel.env'
ПРИМЕНИТЬ = '--apply' in sys.argv


def main():
    if not os.path.exists(ЗАДАНИЕ):
        raise SystemExit(f'нет файла задания {ЗАДАНИЕ}')
    текст = open(ЗАДАНИЕ, encoding='utf-8', errors='replace').read()
    # В задании ключи идут подписями на отдельных строках: «Client Id» и
    # «Client Secret», а само значение — следующей непустой строкой.
    пары = {}
    строки = [с.strip() for с in текст.splitlines()]
    for i, с in enumerate(строки):
        имя = None
        if re.fullmatch(r'client\s*id', с, re.I):
            имя = 'HH_CLIENT_ID'
        elif re.fullmatch(r'client\s*secret', с, re.I):
            имя = 'HH_CLIENT_SECRET'
        if not имя:
            continue
        for j in range(i + 1, min(i + 4, len(строки))):
            зн = строки[j]
            if зн and re.fullmatch(r'[A-Za-z0-9_\-]{20,}', зн):
                пары[имя] = зн
                break
    if len(пары) != 2:
        raise SystemExit(f'в задании нашлось {sorted(пары)} — ожидались обе пары')
    print('нашёл в задании: ' + ', '.join(
        f'{k} ({len(v)} символов)' for k, v in sorted(пары.items())))

    было = []
    if os.path.exists(ENV):
        было = open(ENV, encoding='utf-8-sig', errors='replace').read().splitlines()
    уже = {с.split('=', 1)[0].strip() for с in было if '=' in с}
    print(f'{ENV}: строк {len(было)}, из них уже есть: '
          f'{sorted(уже & set(пары)) or "ни одной"}')
    if not ПРИМЕНИТЬ:
        print('\nсухой прогон. Повторить с --apply')
        return

    shutil.copy2(ENV, ENV + '.bak-' + str(int(time.time()))) if os.path.exists(ENV) else None
    оставить = [с for с in было
                if not any(с.strip().startswith(k + '=') for k in пары)]
    новые = оставить + [f'{k}={v}' for k, v in sorted(пары.items())]
    with open(ENV, 'w', encoding='utf-8', newline='\n') as ф:
        ф.write('\n'.join(новые) + '\n')
        ф.flush()
        os.fsync(ф.fileno())
    # перечитываем файл, а не верим переменной в памяти
    стало = open(ENV, encoding='utf-8-sig', errors='replace').read().splitlines()
    имена = [с.split('=', 1)[0] for с in стало if '=' in с]
    print(f'записано. строк стало {len(стало)}, '
          f'ключи hh на месте: {[и for и in имена if и.startswith("HH_")]}')


if __name__ == '__main__':
    main()
