# -*- coding: utf-8 -*-
r"""Пилот Meyer: сайт для ВСЕХ компаний списка без сайта (владелец 09.10: «как у нас 2600 компаний, а сайт только
у 1700, если мы искали через поиск?»). Это компании, найденные только через каталоги (rusprofile, list-org,
агросервер…) — в выдаче была страница каталога, а не сайт компании; в отборе поиск сайта по названию был
ограничен 150 (баланс). Здесь — без лимита, сначала крупные: xmlriver «название + город официальный сайт»
(EC.find_site_via_xmlriver: карточка компании Яндекса или первый органический результат-не агрегатор).
Чей сайт — потом проверяют kc_audit2 / kc_sayt_proverka / опровергатели, как у всех.
Журнал (fsync, резюм): <набор>-sayty-dobor.jsonl; итог дописывается в <набор>-spisok.json (бэкап рядом).
"""
import io
import json
import os
import re
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import enrich_contacts as EC  # noqa: E402

НАБОР = os.environ.get('POISK_NABOR', 'pilot')
СПИСОК = os.path.join(DIR, НАБОР + '-spisok.json')
ЖУРНАЛ = os.path.join(DIR, НАБОР + '-sayty-dobor.jsonl')
_лок = threading.Lock()


def записать(з):
    with _лок:
        with io.open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def main():
    сп = json.load(io.open(СПИСОК, encoding='utf-8'))
    сделано = {}
    if os.path.exists(ЖУРНАЛ):
        for s in io.open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
                if з.get('итог') in ('найден', 'не найден'):
                    сделано[з['inn']] = з
            except ValueError:
                pass
    без = sorted((к for к in сп['компании'].values() if not к['сайт'] and к['inn'].isdigit() and к['inn'] not in сделано),
                 key=lambda к: -(к.get('выручка') or 0))
    print('без сайта к поиску', len(без), 'уже в журнале', len(сделано), flush=True)
    стоп = {'': ''}

    def найти(к):
        if стоп['']:
            return
        рег = re.sub(r'\b(обл|область|край|респ|республика|г)\b\.?', ' ', к.get('регион') or '').strip()
        try:
            сайт, ист, _ = EC.find_site_via_xmlriver({'name': к['имя'], 'city': рег})
        except Exception as e:  # noqa: BLE001
            записать({'inn': к['inn'], 'итог': 'ошибка', 'ошибка': repr(e)[:100]})
            return
        if 'средств' in (ист or ''):
            стоп[''] = ист
            return
        записать({'inn': к['inn'], 'итог': 'найден' if сайт else 'не найден', 'сайт': сайт or '', 'источник': ист or ''})

    t0 = time.time()
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(найти, без))
    def применить(сп):
        for s in io.open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
            з = json.loads(s)
            к = сп['компании'].get(з['inn'])
            if к is not None and з.get('итог') == 'найден' and not к['сайт']:
                к['сайт'], к['сайт_откуда'] = з['сайт'], 'поиск по названию (%s)' % з.get('источник', '')
    if os.environ.get('PILOT_SNIMKI') == '1':
        # 09.10, волны: отбор мог записать новый снимок списка, пока шли поиски, — перечитываем под замком
        import zamok
        with zamok.замок(СПИСОК):
            сп = zamok.прочитать(СПИСОК)
            применить(сп)
            shutil.copyfile(СПИСОК, СПИСОК + '.bak-' + time.strftime('%d%m-%H%M'))
            zamok.записать_атомарно(СПИСОК, сп)
    else:
        применить(сп)
        shutil.copyfile(СПИСОК, СПИСОК + '.bak-' + time.strftime('%d%m-%H%M'))
        with io.open(СПИСОК, 'w', encoding='utf-8') as f:
            json.dump(сп, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
    shutil.copyfile(СПИСОК, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(СПИСОК)))
    print('готово', json.dumps({'минут': round((time.time() - t0) / 60), 'стоп': стоп[''],
                                'без сайта осталось': sum(1 for к in сп['компании'].values() if not к['сайт'])},
                               ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
