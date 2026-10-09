# -*- coding: utf-8 -*-
"""Расход провайдера по счётчику ключа (09.10): /v1/dashboard/billing/usage -> total_usage в центах за всё время ключа.
Запуск ИЗ СЕССИИ (ключ в окружении сессии): python3 _rashod_provider.py [метка]. Каждый вызов дописывает строку в
rashod-provider.log (в песочнице) и печатает разницу с предыдущим замером и с первым замером с этой меткой.
Траты шага = разница до и после. Ключ не печатается.
"""
import json
import os
import sys
import time
import urllib.request

ЖУРНАЛ = os.environ.get('RASHOD_LOG', os.path.expanduser('~/rashod-provider.log'))


def usage():
    б = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
    з = urllib.request.Request(б + '/v1/dashboard/billing/usage', headers={
        'Authorization': 'Bearer ' + os.environ['PROVIDER_API_KEY'], 'User-Agent': 'curl/8.5.0'})
    return json.load(urllib.request.urlopen(з, timeout=60))['total_usage'] / 100.0  # $


def main():
    метка = sys.argv[1] if len(sys.argv) > 1 else ''
    сейчас = usage()
    прежние = []
    if os.path.exists(ЖУРНАЛ):
        прежние = [json.loads(s) for s in open(ЖУРНАЛ, encoding='utf-8') if s.strip()]
    пред = прежние[-1] if прежние else None
    первый = next((з for з in прежние if метка and з['метка'] == метка), None)
    with open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'время': time.strftime('%Y-%m-%d %H:%M:%S'), 'метка': метка, 'usd': сейчас}, ensure_ascii=False) + '\n')
    print('счётчик $%.2f' % сейчас)
    if пред:
        print('с прошлого замера (%s): $%.2f' % (пред['время'], сейчас - пред['usd']))
    if первый:
        print('с первого замера «%s» (%s): $%.2f' % (метка, первый['время'], сейчас - первый['usd']))


if __name__ == '__main__':
    main()
