# -*- coding: utf-8 -*-
"""Вечный сбор фактов по мере появления страниц в кэше.

Жил только на сервере и терялся при каждом рестарте — теперь лежит в репозитории.

Что изменилось 16.08: пачка идёт ПОТОКАМИ. Последовательно компания стоит 20-30
секунд (карточка луной + новости хайку), а после починки признака «готова»
переразбора ждут 4797 старых паспортов — это больше суток в один поток. И спим
минуту только когда работы нет: раньше пауза стояла между любыми пачками.
"""
import json
import os
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import site_facts  # noqa: E402

PACHKA = int(os.environ.get('FAKTY_PACHKA', '48'))
POTOKOV = int(os.environ.get('FAKTY_POTOKOV', '8'))

while True:
    t0 = time.time()
    try:
        r = site_facts.sobrat(PACHKA, iz_kesha=True, potokov=POTOKOV)
        r['сек'] = round(time.time() - t0)
        pusto = bool(r.get('все_разобраны'))
        print(time.strftime('%H:%M:%S'), json.dumps(r, ensure_ascii=False), flush=True)
    except Exception as e:  # noqa: BLE001
        pusto = True
        print(time.strftime('%H:%M:%S'), 'сбой:', str(e)[:200], flush=True)
    time.sleep(60 if pusto else 2)
