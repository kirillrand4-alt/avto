# -*- coding: utf-8 -*-
r"""Сколько сейчас на сервере и сколько живёт мост."""
import json
import os
import time

д = {'сейчас': time.strftime('%Y-%m-%d %H:%M:%S')}
п = r'C:\seostat\drop\zenno\demon.out'
д['demon_out_обновлён_сек_назад'] = int(time.time() - os.path.getmtime(п))
з = r'C:\seostat\drop\zenno\razbor.pid'
if os.path.exists(з):
    д['razbor_pid'] = open(з, encoding='utf-8').read().strip()[:12]
    д['razbor_pid_обновлён_сек'] = int(time.time() - os.path.getmtime(з))
ж = r'C:\sender\server\zenno_razbor.jsonl'
if os.path.exists(ж):
    д['разбор_журнал_обновлён_сек'] = int(time.time() - os.path.getmtime(ж))
print(json.dumps(д, ensure_ascii=False, indent=1))
