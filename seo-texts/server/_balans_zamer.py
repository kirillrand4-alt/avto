# -*- coding: utf-8 -*-
r"""Точный замер: сколько XMLRiver тратит за отрезок и кто именно тратит.

Владелец 20.08: «хмл ривер не жгёт баланс вообще». По журналу поиска видно
обратное, поэтому меряем не впечатление, а разницу баланса за фиксированный
отрезок и сверяем её с числом пачек за тот же отрезок. Если списано больше,
чем должен был поиск, значит тот же ключ жжёт кто-то ещё.
"""
import json
import os
import sys
import time
import urllib.request

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
os.chdir(DIR)
try:
    import poisk_saytov as PS  # noqa: F401  (поднимает ключи из runner-secrets)
except Exception:  # noqa: BLE001
    pass

U = os.environ.get('XMLRIVER_USER', '')
K = os.environ.get('XMLRIVER_KEY', '')
ЛОГ = r'C:\sender\poisk_saytov.out'
ОТРЕЗОК = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 180


def баланс():
    try:
        return float(urllib.request.urlopen(
            'http://xmlriver.com/api/get_balance/?user=%s&key=%s' % (U, K),
            timeout=25).read().decode('utf-8', 'replace').strip())
    except Exception as e:  # noqa: BLE001
        return None


def пачек():
    if not os.path.exists(ЛОГ):
        return 0
    with open(ЛОГ, encoding='utf-8', errors='replace') as f:
        return sum(1 for s in f if s.strip().startswith('{"взято"'))


б1, п1, t1 = баланс(), пачек(), time.time()
time.sleep(ОТРЕЗОК)
б2, п2, t2 = баланс(), пачек(), time.time()

прошло = max(1.0, t2 - t1)
списано = (б1 - б2) if (б1 is not None and б2 is not None) else None
итог = {
    'отрезок_сек': round(прошло),
    'баланс_было': б1, 'баланс_стало': б2,
    'списано_руб': round(списано, 3) if списано is not None else 'не узнали',
    'пачек_было': п1, 'пачек_стало': п2, 'пачек_за_отрезок': п2 - п1,
}
if списано is not None:
    итог['рублей_в_час'] = round(списано * 3600 / прошло, 1)
    # 25 рублей за тысячу запросов — ставка из poisk_saytov
    итог['запросов_по_балансу'] = round(списано * 1000 / 25)
    итог['запросов_в_час_по_балансу'] = round(
        списано * 1000 / 25 * 3600 / прошло)
    # сколько должен был потратить ТОЛЬКО поиск сайтов
    итог['должен_был_поиск_руб'] = round((п2 - п1) * 12.5, 2)
    лишнее = списано - (п2 - п1) * 12.5
    итог['сверх_поиска_руб'] = round(лишнее, 2)
    итог['вывод'] = ('тратит только поиск' if abs(лишнее) < 3
                     else 'тем же ключом пользуется кто-то ещё'
                     if лишнее > 0 else 'поиск считает больше, чем списано')
print(json.dumps(итог, ensure_ascii=False, indent=1))
