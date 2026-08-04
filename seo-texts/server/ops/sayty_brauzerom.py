# -*- coding: utf-8 -*-
"""Добить «домен не открылся» браузером: молчание прибора — не ответ.

ПОЧЕМУ ЭТО НЕ ПРИДИРКА. Из 72 споров по сайтам 35 остались ничьими, и заметная
часть ничьих — не потому, что признаки равны, а потому что обычный HTTP-ходок
до домена не дошёл: 17 доменов не открылись вовсе. Ставить на этом приговор
значит выдать поломку своего инструмента за свойство мира.

ЧТО У НАС ЕСТЬ. Браузерный ходок с профилями Дельфина на приватных мобильных
прокси и решателем капч. Плюс правило 2-й сессии: целый класс заводских сайтов
отдаёт `Privacy error`, потому что предприятия перешли на сертификаты НУЦ
Минцифры, корня которых в Chromium нет, — лечится вторым заходом с
`ignore_https_errors`. Первый заход честный, флаг только на признак сертификата:
иначе теряется различение подмены там, где оно работает.

Пишу в ТЕ ЖЕ потоки, что и обычный обход, — приговор берёт последнюю запись по
ключу, значит просто перерешает спор с новым знанием.

Запуск: python sayty_brauzerom.py [--vse]
"""
import io
import json
import os
import re
import sys
import time
from collections import Counter

sys.path.insert(0, r'C:\sender\server')

ДОКАЗ = r'C:\seostat\drop\sayty_dokazatelstvo_inn.jsonl'
ЛИЦО = r'C:\seostat\drop\sayty_lico_doma.jsonl'
ПРОФИЛИ = ['829115353', '829115344', '829115332']
_ПРИЗНАК_СЕРТИФИКАТА = ('ERR_CERT_AUTHORITY_INVALID', 'ERR_CERT_', 'Privacy error',
                        'SEC_ERROR', 'CERT_')

ЛАВКА = (('корзин', 3), ('добавить в корзину', 5), ('оформить заказ', 4),
         ('в корзину', 4), ('доставка и оплата', 2), ('способы оплаты', 2),
         ('личный кабинет', 1), ('товаров в каталоге', 3), ('розниц', 2))
ЗАВОД = (('вакансии', 3), ('о предприятии', 4), ('производство', 3),
         ('структура предприятия', 5), ('руководство', 3), ('главный инженер', 5),
         ('отдел снабжения', 5), ('отдел кадров', 3), ('цех', 2),
         ('промышленная безопасность', 4), ('закупки', 3), ('поставщикам', 4))


def взять(url, профиль):
    import browser_probe as BP

    def один(флаг):
        args = {'url': url, 'wait_ms': 6000, 'screenshot': False,
                'ignore_https_errors': флаг, 'solve': True,
                'dolphin_profile': профиль,
                'dolphin_token': os.environ.get('DOLPHIN_TOKEN', '')}
        try:
            return BP.probe(args) or {}
        except Exception as ex:  # noqa: BLE001
            return {'error': f'{type(ex).__name__}: {str(ex)[:160]}'}

    от = один(False)
    беда = str(от.get('error') or '') + ' ' + str(от.get('title') or '')
    как = 'обычно'
    if any(п in беда for п in _ПРИЗНАК_СЕРТИФИКАТА):
        от2 = один(True)
        if not от2.get('error'):
            от, как = от2, 'с отключённой проверкой сертификата (НУЦ Минцифры)'
        else:
            как = 'не открылась даже с отключённой проверкой'
    return (от.get('html') or ''), как, от.get('error'), от.get('http_status')


def main():
    было = {}
    for стр in io.open(ДОКАЗ, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(стр)
        except Exception:
            continue
        было[(str(з.get('inn')), str(з.get('domen')))] = з

    молчали = [з for з in было.values() if not з.get('stranic')]
    if '--vse' not in sys.argv:
        молчали = молчали[:24]
    print(f'доменов, промолчавших обычному ходоку: {len(молчали)}')

    fд = io.open(ДОКАЗ, 'a', encoding='utf-8')
    fл = io.open(ЛИЦО, 'a', encoding='utf-8')
    стат = Counter()
    for н, з in enumerate(молчали):
        д, инн = str(з.get('domen')), str(з.get('inn'))
        профиль = ПРОФИЛИ[н % len(ПРОФИЛИ)]
        html, как, ошибка, статус = взять('https://' + д, профиль)
        ts = time.strftime('%Y-%m-%dT%H:%M:%S')
        if not html:
            стат[f'молчит и в браузере ({str(ошибка)[:28]})'] += 1
            fд.write(json.dumps({**з, 'stranic': 0, 'kak': как,
                                 'oshibka_brauzera': str(ошибка)[:120],
                                 'ts': ts}, ensure_ascii=False) + '\n')
            fд.flush()
            os.fsync(fд.fileno())
            continue
        цифры = ' ' + re.sub(r'\s+', ' ', re.sub(r'[^0-9]', ' ',
                                                re.sub(r'<[^>]+>', ' ', html))) + ' '
        низ = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).lower()
        нов = dict(з)
        нов.update({'stranic': 1, 'kak': как, 'http': статус, 'ts': ts,
                    'inn_nayden': 1 if инн and f' {инн} ' in цифры else 0,
                    'ogrn_nayden': 1 if str(з.get('ogrn') or '') and
                    f" {з.get('ogrn')} " in цифры else 0})
        fд.write(json.dumps(нов, ensure_ascii=False) + '\n')
        л = {'domen': д, 'stranic': 1, 'lavka': 0, 'zavod': 0, 'ts': ts,
             'kak': как}
        for сл, вес in ЛАВКА:
            if сл in низ:
                л['lavka'] += вес
        for сл, вес in ЗАВОД:
            if сл in низ:
                л['zavod'] += вес
        fл.write(json.dumps(л, ensure_ascii=False) + '\n')
        fд.flush()
        fл.flush()
        os.fsync(fд.fileno())
        os.fsync(fл.fileno())
        стат['ОТКРЫЛСЯ В БРАУЗЕРЕ' + (' (сертификат НУЦ)' if 'НУЦ' in как else '')] += 1
        if нов['inn_nayden'] or нов['ogrn_nayden']:
            стат['   и назвал ИНН/ОГРН предприятия'] += 1
    fд.close()
    fл.close()

    print()
    for к, v in sorted(стат.items(), key=lambda x: -x[1]):
        print(f'   {к:52} {v:4}')


if __name__ == '__main__':
    main()
