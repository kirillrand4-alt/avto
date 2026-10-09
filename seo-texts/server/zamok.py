# -*- coding: utf-8 -*-
r"""Замок на файл и атомарная запись JSON (09.10, волны конвейера Meyer).

Зачем: в волнах отбор пишет снимки <набор>-spisok.json порциями, а «сайты по названию» дописывают в тот же файл найденные
сайты. Без замка один затирал бы запись другого. Читатели (обход, проверки) видят файл целиком: запись — во временный
файл и os.replace.

    with замок(путь):            # <путь>.lock, O_EXCL; протухший (старше 15 мин) снимается
        данные = прочитать(путь)
        ...
        записать_атомарно(путь, данные)
"""
import contextlib
import io
import json
import os
import time

ПРОТУХ = 15 * 60


@contextlib.contextmanager
def замок(путь, ждать=900):
    л = путь + '.lock'
    t0 = time.time()
    while True:
        try:
            fd = os.open(л, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, ('%d %s' % (os.getpid(), time.strftime('%Y-%m-%d %H:%M:%S'))).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(л) > ПРОТУХ:
                    os.remove(л)
                    continue
            except OSError:
                pass
            if time.time() - t0 > ждать:
                raise TimeoutError('замок занят: ' + л)
            time.sleep(0.5)
    try:
        yield
    finally:
        try:
            os.remove(л)
        except OSError:
            pass


def прочитать(путь, по_умолчанию=None):
    if not os.path.exists(путь):
        return по_умолчанию
    with io.open(путь, encoding='utf-8') as f:
        return json.load(f)


def записать_атомарно(путь, данные):
    врем = '%s.tmp-%d' % (путь, os.getpid())
    with io.open(врем, 'w', encoding='utf-8') as f:
        json.dump(данные, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    for попытка in range(60):  # Windows: пока файл открыт читателем, replace отказывает — ждём
        try:
            os.replace(врем, путь)
            return
        except PermissionError:
            time.sleep(0.5)
    os.replace(врем, путь)
