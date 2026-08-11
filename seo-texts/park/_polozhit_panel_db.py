# -*- coding: utf-8 -*-
"""Ставит собранную базу панели на место, с копией прежней и проверкой числом.

Прежняя версия просто копировала файл. Теперь: сохраняем прежнюю (можно откатить),
кладём новую и СРАЗУ проверяем запросом, сколько предприятий видит панель — иначе
«положено» ничего не говорит о том, что панель показывает.
"""
import os, shutil, sqlite3, time
SRC = r'C:\seostat\drop\drop-storage\park_panel.db'
DST = r'C:\seostat\data\park_panel.db'


def skolko(put):
    try:
        c = sqlite3.connect('file:%s?mode=ro' % put.replace('\\', '/'), uri=True)
        n = c.execute('select count(*) from predpriyatie').fetchone()[0]
        c.close()
        return n
    except Exception as e:  # noqa: BLE001
        return 'нет числа: %s' % str(e)[:40]


bylo = skolko(DST) if os.path.exists(DST) else 0
if os.path.exists(DST):
    kopiya = DST + '.bak-' + time.strftime('%Y%m%d-%H%M%S')
    shutil.copyfile(DST, kopiya)
    print('прежняя сохранена:', os.path.basename(kopiya))
shutil.copyfile(SRC, DST + '.tmp')
os.replace(DST + '.tmp', DST)
print('положено:', DST, os.path.getsize(DST))
print('предприятий в панели: было %s, стало %s' % (bylo, skolko(DST)))
