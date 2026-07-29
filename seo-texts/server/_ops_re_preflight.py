# -*- coding: utf-8 -*-
"""Преднастройка перемера: убедиться, что на СЕРВЕРЕ лежит починенный код.

Проверяем ровно то, от чего зависят обе цифры:
  * есть ли EC._раскодировать и работает ли он на байтах cp1251;
  * знает ли serverный browser_probe пакет ссылок ('urls');
  * содержит ли hh-разбор починки (номер-менее контакт, рубеж принадлежности);
  * читается ли sales_base.json и сколько там компаний.
"""
import hashlib
import inspect
import json
import os
import sys
import traceback

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import browser_probe as BP    # noqa: E402


def p(*a):
    print(*a)
    sys.stdout.flush()


def main():
    итог = {}
    путь = EC.__file__
    итог['ec_путь'] = путь
    итог['ec_байт'] = os.path.getsize(путь)
    итог['ec_sha8'] = hashlib.sha256(open(путь, 'rb').read()).hexdigest()[:8]
    итог['bp_байт'] = os.path.getsize(BP.__file__)

    # 1. декодер
    итог['есть_раскодировать'] = hasattr(EC, '_раскодировать')
    if итог['есть_раскодировать']:
        сыр = 'Контактное лицо организатора Гоголев Е. А.'.encode('cp1251')
        итог['декод_cp1251'] = EC._раскодировать(
            сыр, 'text/html; charset=windows-1251')
        итог['декод_без_меты'] = EC._раскодировать(сыр, 'text/html')

    # 2. _fetch_site реально зовёт декодер
    src = inspect.getsource(EC._fetch_site)
    итог['fetch_site_зовёт_декодер'] = '_раскодировать' in src

    # 3. дефект _фио
    итог['фио_гоголев'] = EC._фио('Контактное лицо организатора Гоголев Е. А.')
    итог['фио_полн'] = EC._фио('Иванов Иван Иванович')
    итог['фио_иниц'] = EC._фио('Иванов И.И.')
    итог['фио_обр'] = EC._фио('И.И. Иванов')

    # 4. hh-починки
    hsrc = inspect.getsource(EC.hh_lpr_contacts)
    итог['hh_шлёт_пакет'] = "'urls': urls" in hsrc
    итог['hh_контакт_без_номера'] = 'добавлен_номер' in hsrc
    итог['hh_рубеж_по_умолч_закрыт'] = 'hh_страница_наша' in hsrc
    итог['hh_профили'] = EC._HH_DOLPHIN_DEF
    bsrc = inspect.getsource(BP.probe)
    итог['bp_понимает_urls'] = "'urls'" in bsrc or '"urls"' in bsrc
    итог['bp_отдаёт_pages'] = "'pages'" in bsrc or '"pages"' in bsrc

    # 5. агрегаторы
    итог['агрегаторы'] = list(EC._АГРЕГАТОРЫ_ТЕНДЕР)[:20]
    итог['xmlriver'] = bool(os.environ.get('XMLRIVER_USER')) and \
        bool(os.environ.get('XMLRIVER_KEY'))
    if not итог['xmlriver']:
        try:
            итог['xmlriver_secret'] = bool(EC._read_secret('XMLRIVER_USER')) and \
                bool(EC._read_secret('XMLRIVER_KEY'))
        except Exception as ex:  # noqa: BLE001
            итог['xmlriver_secret'] = f'err {ex}'

    # 6. база
    b = r'C:\sender\_ops\sales_base.json'
    итог['база_есть'] = os.path.exists(b)
    if итог['база_есть']:
        d = json.load(open(b, encoding='utf-8'))
        строки = d if isinstance(d, list) else (d.get('rows') or d.get('items') or [])
        итог['база_записей'] = len(строки)
        итог['база_пример'] = строки[:2]
        итог['база_ключи'] = sorted(строки[0].keys())[:20] if строки else []
    p('ИТОГ ' + json.dumps(итог, ensure_ascii=False)[:3000])


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        p('ФАТАЛЬНО:', traceback.format_exc()[-1200:])
