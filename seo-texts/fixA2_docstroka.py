# -*- coding: utf-8 -*-
"""Исправитель A2: в блоке A2 живого web.py пример международного номера в докстроке и
комментарии – заглушка «+374 00 000-000» вместо настоящего номера (правило репо: реальные
номера только в базе). Меняются только комментарий и докстрока – поведение то же, перезапуск
не нужен (новый текст подхватится при следующем). Под замком, с бэкапом и compile-проверкой.

    python3 zapusk_na_servere.py fixA2_docstroka.py
"""
import io
import os
import re
import shutil
import time

KOREN = r'C:\centro2'
WEB = os.path.join(KOREN, 'app', 'web.py')
ZAMOK = r'C:\centro2\_zamok.txt'
METKA = '# ------------------------------------------------- вид контакта по данным каталога (исправитель A2'


def vzyat_zamok(kto):
    if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
        os.remove(ZAMOK)
    try:
        fd = os.open(ZAMOK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print('ЗАМОК ЗАНЯТ: ' + io.open(ZAMOK, encoding='utf-8').read())
        raise SystemExit(3)
    os.write(fd, ('%s %s' % (kto, time.strftime('%H:%M:%S'))).encode('utf-8'))
    os.close(fd)


def otdat_zamok():
    try:
        os.remove(ZAMOK)
    except OSError:
        pass


ZAMENY = [
    (re.compile(r'^(    """«)\+374\d{8}(» -> \{"pokaz": «)\+374 \d\d \d{3}-\d{3}(», "strana": «Армения»\}\.)$', re.M),
     r'\g<1>+37400000000\g<2>+374 00 000-000\g<3>'),
    (re.compile(r'^(# \(«)\+374 \d\d \d{3}-\d{3}(»\), уровень ЛПР)', re.M),
     r'\g<1>+374 00 000-000\g<2>'),
]

vzyat_zamok('fixA2 (докстрока web.py, без перезапуска)')
try:
    t = io.open(WEB, encoding='utf-8').read()
    i = t.find(METKA)
    if i < 0:
        print('блока A2 в web.py нет – ничего не делаю')
        raise SystemExit(1)
    golova, blok = t[:i], t[i:]
    novyy = blok
    for rx, na in ZAMENY:
        novyy, n = rx.subn(na, novyy)
        print('замен: %d' % n)
    if novyy == blok:
        print('уже заглушки – ничего не меняю')
        raise SystemExit(0)
    itog = golova + novyy
    # меняются только комментарий и докстрока; файл обязан компилироваться
    compile(itog, 'web.py', 'exec')
    bekap = os.path.join(KOREN, '_bekap', time.strftime('fixA2-doc-%Y%m%d-%H%M%S'))
    os.makedirs(bekap, exist_ok=True)
    shutil.copy2(WEB, os.path.join(bekap, 'web.py'))
    io.open(WEB, 'w', encoding='utf-8').write(itog)
    print('записано; бэкап: %s; строк до/после: %d/%d' % (bekap, t.count('\n'), itog.count('\n')))
    print('в блоке A2 осталось «+374 00 000-000»: %d, других +374 с цифрами: %d' % (
        itog[i:].count('+374 00 000-000'), len(re.findall(r'\+374 ?[1-9]', itog[i:]))))
finally:
    otdat_zamok()
