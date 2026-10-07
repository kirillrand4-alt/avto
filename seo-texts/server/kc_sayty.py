# -*- coding: utf-8 -*-
r"""База КЦ, шаг 3б: сайт для компаний, у которых его нет ни в нашей базе, ни в реестровой
карточке (или там агрегатор вроде partner-reestr.ru). Поиск — xmlriver (Яндекс, карточка
компании + органика, enrich_contacts.find_site_via_xmlriver), фильтр агрегаторов — _is_own_site.
Найденный сайт проходит тот же обход, что в kc_kontakty (номера на живых страницах, подписи,
описание), плюс проверка принадлежности: ИНН компании на страницах или ядро названия в тексте.
Выход (fsync, резюм по ИНН): C:\sender\server\kc-sayty.jsonl -> копия на дроп.
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
import kc_kontakty as KK  # noqa: E402
import enrich_contacts as EC  # noqa: E402
import meyer_nalichie as MN  # noqa: E402
import meyer_proverka as MP  # noqa: E402

ВЫХОД = os.path.join(DIR, 'kc-sayty.jsonl')
_лок = threading.Lock()
ОПФ = re.compile(r'^(ООО|АО|ПАО|ЗАО|ОАО|НАО|АПФ|ПК|СПК|КФХ|МУП|ГУП|ФГУП)\s+', re.I)


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def ядра(имя):
    out = set()
    for кус in re.findall(r'[«"]+([^«»"]{3,})[»"]+', имя or ''):
        out.add(re.sub(r'\s+', ' ', кус).strip().lower())
    голое = ОПФ.sub('', re.sub(r'[«»"]', ' ', имя or '')).strip()
    if len(голое) >= 4:
        out.add(re.sub(r'\s+', ' ', голое).lower())
    return {я for я in out if len(я) >= 4}


def чей_сайт(к, рез):
    if к['inn'] in (рез.get('инн_живой') or []):
        return 'свой: ИНН компании на сайте'
    тексты = []
    for u, ст in рез.get('страницы', [])[:3]:
        if ст == 'ok':
            _, html, _ = MN.скачать(u)
            тексты.append(MP.в_текст(html or '').lower().replace('«', '"').replace('»', '"'))
    т = ' '.join(тексты)
    for я in ядра(к['имя']):
        if я in т:
            return 'по названию: «%s» на сайте' % я
    return 'не подтверждён: ни ИНН, ни названия на сайте'


def одна(к, прежний):
    з = {'inn': к['inn']}
    try:
        регион = re.sub(r'\b(обл|область|край|респ|республика|г)\b\.?', ' ', к.get('регион') or '').strip()
        сайт, ист, card = EC.find_site_via_xmlriver({'name': к['имя'], 'city': регион})
        з['поиск'] = {'сайт': сайт, 'источник': ист, 'кандидаты': (card or {}).get('_kandidaty', [])[:4]}
        if сайт:
            рез = KK.обход(к, сайт)
            з.update(рез)
            з['сайт_чей'] = чей_сайт(к, рез)
        if not сайт and re.search(r'закончились средства|перезапрос|err', ист or '', re.I):
            з['итог'] = 'ошибка поиска: ' + (ист or '')[:60]  # повторить после пополнения xmlriver
        else:
            з['итог'] = 'ok'
    except Exception as e:  # noqa: BLE001
        з['итог'] = 'сбой: ' + repr(e)[:120]
    записать(з)


def main():
    сп = json.load(io.open(os.path.join(DIR, 'kc-spisok.json'), encoding='utf-8'))['компании']
    прежние = {}
    for s in io.open(os.path.join(DIR, 'kc-kontakty.jsonl'), encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('итог') == 'ok':
            прежние[з['inn']] = з
    сделано = set()
    if os.path.exists(ВЫХОД):
        for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
                if з.get('итог') == 'ok' and not re.search(r'закончились средства|перезапрос',
                                                          (з.get('поиск') or {}).get('источник') or ''):
                    сделано.add(з['inn'])
            except ValueError:
                pass
    очередь = []
    for i, з in прежние.items():
        if i in сделано or i not in сп:
            continue
        сайт = з.get('сайт') or ''
        if not сайт or not EC._is_own_site(сайт) or not any(ст == 'ok' for _, ст in з.get('страницы', [])):
            очередь.append(сп[i])
    print('без своего сайта', len(очередь), flush=True)
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda к: одна(к, прежние.get(к['inn'])), очередь))
    shutil.copyfile(ВЫХОД, r'C:\seostat\drop\drop-storage\kc-sayty.jsonl')
    print('готово', flush=True)


if __name__ == '__main__':
    main()
