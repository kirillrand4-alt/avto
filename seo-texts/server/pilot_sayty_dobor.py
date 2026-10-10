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
import enrich_contacts as EC
import meyer_nalichie as MN  # noqa: E402
import sayt_po_nazvaniyu as SN  # noqa: E402  (проверка найденного сайта)

НАБОР = os.environ.get('POISK_NABOR', 'pilot')
СПИСОК = os.path.join(DIR, НАБОР + '-spisok.json')
ЖУРНАЛ = os.path.join(DIR, НАБОР + '-sayty-dobor.jsonl')
ОШИБКА_XML = re.compile(r'аняты все|429|перезапрос|xmlriver-err|timed out|timeout', re.I)
_лок = threading.Lock()


def записать(з):
    with _лок:
        with io.open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def применить_журнал(сп, журнал):
    """Журнал сайтов по названию -> список: решает ПОСЛЕДНЯЯ запись по ИНН (10.10: перепроверка дописывает «отклонён»);
    отклонённый сайт, поставленный этим шагом, снимается."""
    посл = {}
    for s_ in io.open(журнал, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s_)
        except ValueError:
            continue
        if з.get('inn'):
            посл[з['inn']] = з
    for i, з in посл.items():
        к = сп['компании'].get(i)
        if к is None:
            continue
        if з.get('итог') == 'найден' and not к.get('сайт'):
            к['сайт'], к['сайт_откуда'] = з['сайт'], 'поиск по названию (%s)' % з.get('источник', '')
        elif з.get('итог') == 'отклонён' and str(к.get('сайт_откуда') or '').startswith('поиск по названию') \
                and MN.домен(к.get('сайт') or '') == MN.домен(з.get('сайт') or ''):
            к['сайт_был'], к['сайт'], к['сайт_откуда'] = к['сайт'], '', 'поиск по названию: отклонён (%s)' % з.get('почему', '')


def main():
    сп = json.load(io.open(СПИСОК, encoding='utf-8'))
    сделано = {}
    if os.path.exists(ЖУРНАЛ):
        for s in io.open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
                # 10.10, ревизия: 2212 из 2250 «не найден» были ошибками xmlriver («Заняты все каналы», 429,
                # «перезапрос») — такие не «сделано», перезапрашиваются
                if з.get('итог') in ('найден', 'отклонён') or (з.get('итог') == 'не найден' and not ОШИБКА_XML.search(з.get('источник') or '')):
                    сделано[з['inn']] = з
            except ValueError:
                pass
    без = sorted((к for к in сп['компании'].values() if not к['сайт'] and к['inn'].isdigit() and к['inn'] not in сделано),
                 key=lambda к: -(к.get('выручка') or 0))
    # 09.10, полный прогон: потолок поисков на весь набор (бюджет xmlriver 3,3 тыс. ₽: поиск ~1,9, агенты ~0,5) —
    # сначала крупные, хвост мелких без сайта остаётся без поиска сайта; 0 — без потолка
    потолок = int(os.environ.get('PILOT_SAYTY_MAX', '0'))
    if потолок:
        без = без[:max(0, потолок - len(сделано))]
    print('без сайта к поиску', len(без), 'уже в журнале', len(сделано), flush=True)
    стоп = {'': ''}
    найдено_дом = {i: MN.домен(з.get('сайт') or '') for i, з in сделано.items() if з.get('итог') == 'найден'}
    _лок_д = threading.Lock()

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
        if not сайт and ОШИБКА_XML.search(ист or ''):
            записать({'inn': к['inn'], 'итог': 'ошибка', 'ошибка': ист})
            return
        if сайт:  # 10.10: агрегаторы, реестры, чужие сайты — не принимаем (sayt_po_nazvaniyu)
            with _лок_д:
                чужой = any(д == MN.домен(сайт) and и != к['inn'] for и, д in найдено_дом.items())
                найдено_дом[к['inn']] = MN.домен(сайт)
            принят, почему = SN.проверить(к['имя'], к['inn'], сайт, чужой, к.get('регион') or '', к.get('сегм') or '')
            if not принят:
                записать({'inn': к['inn'], 'итог': 'отклонён', 'сайт': сайт, 'источник': ист or '', 'почему': почему})
                return
        записать({'inn': к['inn'], 'итог': 'найден' if сайт else 'не найден', 'сайт': сайт or '', 'источник': ист or ''})

    t0 = time.time()
    # 09.10, полный прогон: 8 потоков вместе с поиском (10) и поисками обогателя в обходе давали xmlriver HTTP 429
    # (38% запросов поиска за полчаса) — по умолчанию 3
    with ThreadPoolExecutor(int(os.environ.get('PILOT_SAYTY_POTOKOV', '3'))) as ex:
        list(ex.map(найти, без))
    def применить(сп):
        применить_журнал(сп, ЖУРНАЛ)
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
