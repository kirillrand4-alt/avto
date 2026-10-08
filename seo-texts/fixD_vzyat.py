# -*- coding: utf-8 -*-
"""fixD: только чтение. Копия каталога meyer_baza1.db (sqlite backup API, без записи в боевую
базу) и назначений продаж – на дроп, для разбора «чей сайт», описаний и холдингов."""
import os
import sqlite3
import time
import zipfile

D = r'C:\seostat\drop\drop-storage'
zp = os.path.join(D, 'fixD-katalog.zip')
with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
    for imya in ('meyer_baza1.db', 'centro_sales_meyer1.db'):
        src = sqlite3.connect('file:%s?mode=ro' % os.path.join(r'C:\centro2\data', imya), uri=True)
        tmp = os.path.join(D, 'fixD-tmp-' + imya)
        if os.path.exists(tmp):
            os.remove(tmp)
        dst = sqlite3.connect(tmp)
        src.backup(dst)
        dst.close()
        src.close()
        z.write(tmp, imya)
        os.remove(tmp)
print('каталог: %s %d байт' % (zp, os.path.getsize(zp)))
print('замок:', os.path.exists(r'C:\centro2\_zamok.txt'), time.strftime('%H:%M:%S'))
