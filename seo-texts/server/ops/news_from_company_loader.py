# -*- coding: utf-8 -*-
"""Загрузчик: берёт свежий newsco_op.py из drop-storage и выполняет его.

Смысл: раннер занят другими агентами, каждый panel_file_put — отдельное задание
в общей очереди. Код кладём на дроп обычным `drop_client.sh up` (очередь не
трогаем), а раннером зовём только этот загрузчик — одно задание на прогон.
"""
import os
import sys
import urllib.request

ПУТЬ = r'C:\seostat\drop\drop-storage\newsco_op.py'


def _исходник():
    if os.path.exists(ПУТЬ):
        return open(ПУТЬ, 'rb').read().decode('utf-8')
    url = (os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
           .rstrip('/') + '/newsco_op.py')
    req = urllib.request.Request(
        url, headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    return urllib.request.urlopen(req, timeout=90).read().decode('utf-8')


src = _исходник()
sys.stderr.write('loader: %d байт кода\n' % len(src))
g = {'__name__': '__main__', '__file__': ПУТЬ}
exec(compile(src, ПУТЬ, 'exec'), g)
