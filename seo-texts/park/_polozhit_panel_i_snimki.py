# -*- coding: utf-8 -*-
"""Ставит базу панели и КОПИРУЕТ снимки номеров в статику, откуда панель их отдаёт.

Снимки делаются в хранилище дропа (`drop-storage`), а панель раздаёт из
`app\\static\\centro\\dokaz`. Без этого шага ссылка «📷 номер доказан» в списке вела бы
на 404 — картинка есть, а панель её не видит.
"""
import glob, os, shutil, sqlite3, time
SRC = r'C:\seostat\drop\drop-storage\park_panel.db'
DST = r'C:\seostat\data\park_panel.db'
SNIM_IZ = r'C:\seostat\drop\drop-storage'
SNIM_V = r'C:\seostat\app\static\centro\dokaz'


def skolko(put, zapros):
    try:
        c = sqlite3.connect('file:%s?mode=ro' % put.replace('\\', '/'), uri=True)
        n = c.execute(zapros).fetchone()[0]
        c.close()
        return n
    except Exception as e:  # noqa: BLE001
        return 'нет числа: %s' % str(e)[:40]


bylo = skolko(DST, 'select count(*) from predpriyatie') if os.path.exists(DST) else 0
if os.path.exists(DST):
    shutil.copyfile(DST, DST + '.bak-' + time.strftime('%Y%m%d-%H%M%S'))
# Пишем ПОВЕРХ, а не через .tmp + os.replace: файл открыт службой панели, и замена
# отваливается «Access is denied». Копия для отката снята строкой выше.
shutil.copyfile(SRC, DST)
print('предприятий в панели: было %s, стало %s' % (bylo, skolko(DST, 'select count(*) from predpriyatie')))
print('из них с доказанным снимком номера: %s'
      % skolko(DST, "select count(*) from predpriyatie where coalesce(nomer_snimok,'')<>''"))

perenes = 0
for put in glob.glob(os.path.join(SNIM_IZ, 'NOMER-*.png')):
    cel = os.path.join(SNIM_V, os.path.basename(put))
    if not os.path.exists(cel) or os.path.getsize(cel) != os.path.getsize(put):
        shutil.copyfile(put, cel)
        perenes += 1
print('снимков номеров перенесено в статику: %d (всего в статике %d)'
      % (perenes, len(glob.glob(os.path.join(SNIM_V, 'NOMER-*.png')))))
