# -*- coding: utf-8 -*-
"""Где на сервере лежит боевой конвейер и кто пишет phone_contacts."""
import glob
import hashlib
import json
import os


def main():
    out = {}
    hits = []
    for root in (r'C:\sender', r'C:\seostat'):
        for p in glob.glob(os.path.join(root, '**', 'enrich_*.py'), recursive=True):
            try:
                b = open(p, 'rb').read()
            except OSError:
                continue
            hits.append({'путь': p, 'байт': len(b),
                         'sha': hashlib.sha256(b).hexdigest()[:12],
                         'пишет_phone_contacts': b'phone_contacts' in b})
    out['файлы_конвейера'] = sorted(hits, key=lambda x: -x['байт'])[:20]

    # кто вообще упоминает phone_contacts под C:\sender
    writers = []
    for p in glob.glob(r'C:\sender\**\*.py', recursive=True):
        try:
            b = open(p, 'rb').read()
        except OSError:
            continue
        if b'phone_contacts' in b:
            writers.append({'путь': p, 'байт': len(b),
                            'есть_INSERT': b'INSERT INTO phone_contacts' in b
                            or b'insert into phone_contacts' in b})
    out['упоминают_phone_contacts'] = writers[:25]
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
