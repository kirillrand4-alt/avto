# -*- coding: utf-8 -*-
"""fixC: в docstring _shared_phone_keys реальный номер-пример заменить заглушкой (правило:
в коде реальные номера – только заглушки). Под замком; поведение не меняется – без перезапуска."""
import io
import os
import shutil
import time

FAJL = r'C:\centro2\app\services\centro_catalog.py'
ZAMOK = r'C:\centro2\_zamok.txt'
if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
    os.remove(ZAMOK)
try:
    fd = os.open(ZAMOK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
except FileExistsError:
    print('ЗАМОК ЗАНЯТ: ' + io.open(ZAMOK, encoding='utf-8').read())
    raise SystemExit(3)
os.write(fd, ('fixC (docstring) %s' % time.strftime('%H:%M:%S')).encode('utf-8'))
os.close(fd)
try:
    t = io.open(FAJL, encoding='utf-8').read()
    staro = '«+7 3452 XX-XX-XX доб. 4530» (реальный номер скрыт; правка уже применена) и\n    «… доб. 4713»'
    novo = '«+7 495 000-00-00 доб. 101» и\n    «… доб. 102»'
    if novo in t:
        print('[уже]')
    elif t.count(staro) == 1:
        nt = t.replace(staro, novo, 1)
        compile(nt, FAJL, 'exec')
        bek = os.path.join(r'C:\centro2\_bekap', time.strftime('fixC-kod3-%Y%m%d-%H%M%S'))
        os.makedirs(bek, exist_ok=True)
        shutil.copy2(FAJL, os.path.join(bek, 'centro_catalog.py'))
        io.open(FAJL, 'w', encoding='utf-8').write(nt)
        print('[ок] docstring исправлен, копия %s' % bek)
    else:
        print('якорь найден %d раз – не правлю' % t.count(staro))
finally:
    try:
        os.remove(ZAMOK)
    except OSError:
        pass
