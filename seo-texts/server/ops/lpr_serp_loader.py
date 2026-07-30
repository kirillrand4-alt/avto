# -*- coding: utf-8 -*-
"""Загрузчик: берёт свежий lpr_op.py из drop-storage и выполняет его.

Тот же приём, что и у newsco_loader: раннер разбирает задания ПО ОДНОМУ и делится
с другими агентами, поэтому panel_file_put на каждую правку кода — расточительство.
Код кладём на дроп обычным `drop_client.sh up ... lpr_op.py`, а раннером зовём
только этот загрузчик.
"""
import os
import sys
import urllib.request

ПУТЬ = r'C:\seostat\drop\drop-storage\lpr_op.py'


def _исходник():
    if os.path.exists(ПУТЬ):
        return open(ПУТЬ, 'rb').read().decode('utf-8')
    url = (os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
           .rstrip('/') + '/lpr_op.py')
    req = urllib.request.Request(
        url, headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    return urllib.request.urlopen(req, timeout=90).read().decode('utf-8')


src = _исходник()
sys.stderr.write('loader: %d байт кода\n' % len(src))
g = {'__name__': '__main__', '__file__': ПУТЬ}
exec(compile(src, ПУТЬ, 'exec'), g)
