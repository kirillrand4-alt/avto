# -*- coding: utf-8 -*-
r"""Перенести сырьё Зенки (zenno\razobrano) с рабочего диска C: на D:.

Владелец 29.08: «давай сначала перекинем все эти страницы на второй диск, а
потом будем вытягивать адреса, их роли со страниц и номера телефонов».

ЗАЧЕМ. В razobrano 136 ГБ сырых страниц — 887 тысяч файлов. Раньше их считали
отработанными и удаляли: chistka_razobrano.py прямо пишет «содержимое не читает
никто», и 18.08 по этому основанию снесли 241 869 файлов. Проверка 29.08
показала, что рассуждение неверное: из ста компаний у 68 в сыром HTML нашлись
адреса, которых нет в базе — 169 новых на 175 найденных. «Никто не читает» и
«там ничего нет» — разные вещи, и вторая оказалась ложной.

Поэтому сначала переносим на D: (там 371 ГБ свободно), а извлекаем потом, уже
без давления по месту на рабочем диске.

СВЕЖИЕ СУТКИ НЕ ТРОГАЕМ. Мост определяет «Зенка встала» по свежести файлов в
gotovo и razobrano (dorabotka: tishina_min). Убрав всё, мы обнулим этот сигнал,
и сторож решит, что шаблон молчит.

ПЕРЕНОС, А НЕ КОПИЯ: файл удаляется с C: только после того, как копия на D:
совпала по размеру. Прогон резюмируемый — что уже перенесено, пропускается.

    python perenos_razobrano.py             посчитать, ничего не трогая
    python perenos_razobrano.py --delat     переносить
    python perenos_razobrano.py --delat 3   переносить старше трёх дней
"""
import json
import os
import shutil
import sys
import time

ОТКУДА = os.environ.get('RAZOBRANO_DIR', r'C:\seostat\drop\zenno\razobrano')
КУДА = os.environ.get('RAZOBRANO_DEST', r'D:\zenno-razobrano')
ЖУРНАЛ = r'D:\zenno-razobrano-perenos.jsonl'
ОТЧЁТ_КАЖДЫЕ = 2000


def _журнал(запись):
    with open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
        f.write(json.dumps(запись, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


def перенос(дней=1, делать=False):
    порог = time.time() - дней * 86400
    итог = {'откуда': ОТКУДА, 'куда': КУДА, 'держим_дней': дней,
            'файлов': 0, 'свежих_оставили': 0, 'перенесено': 0,
            'уже_было': 0, 'ошибок': 0, 'гб_перенесено': 0.0,
            'гб_под_перенос': 0.0}
    if делать:
        os.makedirs(КУДА, exist_ok=True)
    t0 = time.time()
    # scandir потоково: список в память не берём, в каталоге 887 тысяч записей
    with os.scandir(ОТКУДА) as это:
        for з in это:
            try:
                if not з.is_file():
                    continue
                ст = з.stat()
            except OSError:
                итог['ошибок'] += 1
                continue
            итог['файлов'] += 1
            if ст.st_mtime >= порог:
                итог['свежих_оставили'] += 1
                continue
            итог['гб_под_перенос'] += ст.st_size / 2**30
            if not делать:
                continue
            цель = os.path.join(КУДА, з.name)
            try:
                if os.path.exists(цель) and os.path.getsize(цель) == ст.st_size:
                    os.remove(з.path)          # копия уже есть и целая
                    итог['уже_было'] += 1
                    continue
                shutil.copy2(з.path, цель)
                if os.path.getsize(цель) != ст.st_size:
                    итог['ошибок'] += 1
                    continue                   # оригинал НЕ трогаем
                os.remove(з.path)
                итог['перенесено'] += 1
                итог['гб_перенесено'] += ст.st_size / 2**30
            except Exception:  # noqa: BLE001
                итог['ошибок'] += 1
            if итог['перенесено'] and итог['перенесено'] % ОТЧЁТ_КАЖДЫЕ == 0:
                _журнал({'ts': time.strftime('%H:%M:%S'),
                         'перенесено': итог['перенесено'],
                         'гб': round(итог['гб_перенесено'], 1),
                         'секунд': round(time.time() - t0),
                         'ошибок': итог['ошибок']})
    итог['гб_под_перенос'] = round(итог['гб_под_перенос'], 1)
    итог['гб_перенесено'] = round(итог['гб_перенесено'], 1)
    итог['секунд'] = round(time.time() - t0)
    try:
        вс, исп, своб = shutil.disk_usage(r'C:\\')
        итог['свободно_на_C_гб'] = round(своб / 2**30, 1)
        вс, исп, своб = shutil.disk_usage(r'D:\\')
        итог['свободно_на_D_гб'] = round(своб / 2**30, 1)
    except Exception:  # noqa: BLE001
        pass
    if делать:
        _журнал({'ts': time.strftime('%H:%M:%S'), 'ИТОГ': итог})
    return итог


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    делать = '--delat' in a
    дней = 1
    for х in a:
        if х.isdigit():
            дней = int(х)
    print(json.dumps(перенос(дней, делать), ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
