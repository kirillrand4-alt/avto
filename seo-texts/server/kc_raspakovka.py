# -*- coding: utf-8 -*-
r"""Распаковка архива «01. НАШИ ПРОЕКТЫ - КЦ», залитого владельцем на дроп частями
(upload_kp_arhiv.ps1: kc-proekty-ДДММ-ЧЧММ.tar.part001.. + .ready.txt с размером, SHA256, числом
файлов). Части читаются подряд как один поток (склеенный tar на диск не пишется), по пути
считается SHA256, файлы распаковываются в C:\seostat\kc-proekty\ с исходной структурой папок.
Небезопасные пути (абсолютные, «..») пропускаются (filter='data').

Запуск: python kc_raspakovka.py kc-proekty-0610-1436.tar   (детачем — _pusk_raspakovki.py)
Итог: C:\sender\server\kc-raspakovka.json (+ копия на дроп).
"""
import hashlib
import io
import json
import os
import shutil
import sys
import tarfile
import time

ДРОП = r'C:\seostat\drop\drop-storage'
КУДА = r'C:\seostat\kc-proekty'
ИТОГ = r'C:\sender\server\kc-raspakovka.json'


class Части(io.RawIOBase):
    """Части по порядку как один читаемый поток + SHA256 по пути."""
    def __init__(self, пути):
        self.пути, self.i, self.f = list(пути), 0, None
        self.sha = hashlib.sha256()
        self.прочитано = 0

    def readable(self):
        return True

    def readinto(self, b):
        while True:
            if self.f is None:
                if self.i >= len(self.пути):
                    return 0
                self.f = open(self.пути[self.i], 'rb')
                self.i += 1
            n = self.f.readinto(b)
            if n:
                self.sha.update(memoryview(b)[:n])
                self.прочитано += n
                return n
            self.f.close()
            self.f = None


def main():
    имя = sys.argv[1]
    ready = {}
    for s in io.open(os.path.join(ДРОП, имя + '.ready.txt'), encoding='ascii', errors='replace'):
        if '=' in s:
            k, v = s.strip().split('=', 1)
            ready[k] = v
    части = [os.path.join(ДРОП, p) for p in ready['parts'].split(',')]
    o = {'архив': имя, 'ожидается_байт': int(ready['bytes']), 'ожидается_файлов': int(ready['files']),
         'частей': len(части), 'все_части_есть': all(os.path.exists(p) for p in части),
         'куда': КУДА, 'начало': time.strftime('%Y-%m-%d %H:%M:%S')}
    своб = shutil.disk_usage(os.path.splitdrive(КУДА)[0] + '\\').free
    o['свободно_ГБ'] = round(своб / 1e9, 1)
    if not o['все_части_есть'] or своб < int(ready['bytes']) * 1.1:
        o['итог'] = 'стоп: нет частей' if not o['все_части_есть'] else 'стоп: мало места на диске'
        json.dump(o, io.open(ИТОГ, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(json.dumps(o, ensure_ascii=False))
        return
    os.makedirs(КУДА, exist_ok=True)
    поток = io.BufferedReader(Части(части), buffer_size=8 << 20)
    файлов, пропущено, примеры = 0, [], []
    with tarfile.open(fileobj=поток, mode='r|') as tar:
        for m in tar:
            if m.name.startswith(('/', '\\')) or '..' in m.name.replace('\\', '/').split('/'):
                пропущено.append(m.name[:120])
                continue
            try:
                tar.extract(m, КУДА, filter='data')
            except Exception as e:  # noqa: BLE001
                пропущено.append('%s: %s' % (m.name[:100], repr(e)[:80]))
                continue
            if m.isfile():
                файлов += 1
                if len(примеры) < 8 and any('\u0400' <= ch <= '\u04ff' for ch in m.name):
                    примеры.append(m.name[:150])
                if файлов % 2000 == 0:
                    print('файлов', файлов, flush=True)
    # дочитать хвост (выравнивание tar), чтобы хеш был по всему архиву
    while поток.read(8 << 20):
        pass
    o.update({'распаковано_файлов': файлов, 'пропущено': пропущено[:30], 'пропущено_всего': len(пропущено),
              'прочитано_байт': поток.raw.прочитано, 'sha256_совпал': поток.raw.sha.hexdigest() == ready['sha256'],
              'примеры_русских_имён': примеры, 'верхние_папки': sorted(os.listdir(КУДА))[:10],
              'конец': time.strftime('%Y-%m-%d %H:%M:%S')})
    o['итог'] = 'ok' if (o['sha256_совпал'] and файлов == o['ожидается_файлов']) else 'расхождение — смотри поля'
    with io.open(ИТОГ, 'w', encoding='utf-8') as f:
        json.dump(o, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    shutil.copyfile(ИТОГ, os.path.join(ДРОП, 'kc-raspakovka.json'))
    print(json.dumps(o, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
