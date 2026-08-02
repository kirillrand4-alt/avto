# -*- coding: utf-8 -*-
"""Выложить файлы приложения на дроп, чтобы править их у себя.

Панель обзвона живёт в `C:\\seostat\\app`, а не под `C:\\sender`, поэтому
штатный `panel_file_put --get` до неё не дотягивается. Правки в 25-килобайтный
шаблон вслепую делать нельзя, значит его надо сначала прочитать целиком.

Только ЧТЕНИЕ и только из двух корней приложения — ни записи, ни выхода за
их пределы.

Запуск: python vylozhit_fayly.py <относительный путь> [ещё пути...]
"""
import os
import sys
import urllib.request

КОРНИ = (r'C:\seostat', r'C:\sender')


def на_дроп(путь, имя):
    урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
    зпр = urllib.request.Request(
        урл.rstrip('/') + '/' + имя, data=open(путь, 'rb').read(), method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    with urllib.request.urlopen(зпр, timeout=300) as о:
        return о.read()[:120]


def main():
    for отн in sys.argv[1:]:
        п = os.path.abspath(отн if os.path.isabs(отн)
                            else os.path.join(КОРНИ[0], отн))
        if not any(п.lower().startswith(к.lower()) for к in КОРНИ) or '..' in отн:
            print(f'ОТКАЗ, путь вне приложения: {отн}')
            continue
        if not os.path.exists(п):
            print(f'НЕТ ФАЙЛА: {п}')
            continue
        имя = 'src_' + os.path.basename(п)
        try:
            на_дроп(п, имя)
            print(f'{имя}  <- {п}  ({os.path.getsize(п)} байт)')
        except Exception as e:  # noqa: BLE001
            print(f'НЕ ЛЕГЛО {имя}: {str(e)[:120]}')


if __name__ == '__main__':
    main()
