# -*- coding: utf-8 -*-
"""Телефон предприятия по ЕГО НАЗВАНИЮ — в том числе на сайте холдинга.

48 целевых предприятий имеют названного технического руководителя (197 человек)
и НИ ОДНОГО номера — ни личного, ни заводского. Звонить некуда, хотя известно
кому.

У 25 из них есть кандидат-сайт, и он, как правило, ПРАВИЛЬНЫЙ, просто
холдинговый: «АО "Катавский цемент"» → cemros.ru, «АО "ОДК-ГТ"» → uecrus.com,
«АО "Сокольский ЦБК"» → sokolmill.ru. ИНН завода на сайте холдинга не печатают
— поэтому наш рубеж и не пропустил домен в подтверждённые, и это правильно.
Но ТЕЛЕФОН завода там печатают, на странице «предприятия» или «контакты».

Поэтому ищем не ИНН и не человека, а НАЗВАНИЕ ПРЕДПРИЯТИЯ, и берём номер из
окна вокруг него. Записывается номер БЕЗ привязки к человеку: это телефон
организации, а не чей-то личный, и выдавать его за личный нельзя.

Рубежи: `без_графики` до разбора, телефоны только через `phones_in`, запись
только через `add_phone`, номер только из окна вокруг названия. Имя ищем в
двух видах — официальное краткое и «ядро» без кавычек и формы собственности,
потому что на сайте холдинга пишут «Катавский цемент», а не «АО "Катавский
цемент"».

Durable: журнал `nomer_predpriyatiya.jsonl` с находками поимённо.

Запуск: python nomer_predpriyatiya.py [--lim N] [--potokov N] [--budget СЕК] [--apply]
"""
import io
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB       # noqa: E402
import enrich_contacts as EC  # noqa: E402

ПРИМЕНИТЬ = '--apply' in sys.argv


def арг(имя, поум):
    return sys.argv[sys.argv.index(имя) + 1] if имя in sys.argv else поум


ЛИМ = int(арг('--lim', '80'))
ПОТОКОВ = int(арг('--potokov', '8'))
БЮДЖЕТ = float(арг('--budget', '900'))
ЖУРНАЛ = r'C:\sender\server\nomer_predpriyatiya.jsonl'
ТЕХ = set(EDB.EnrichDB.TECH_ROLES)
_ЗАМОК = threading.Lock()

_ПОХОЖЕ = re.compile(
    r'контакт|предприяти|завод|производств|структур|подразделен|филиал|'
    r'где\s*мы|адрес|kontakt|contact|plant|factory|about|company|geografi|'
    r'karta|map', re.I)
_ССЫЛКА = re.compile(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.{0,120}?)</a>',
                     re.I | re.S)
_ТЕГИ = re.compile(r'<[^>]+>')
_ОКНО = 300
_ФОРМЫ = re.compile(
    r'\b(ООО|ОАО|ЗАО|АО|ПАО|НАО|МУП|ГУП|ФГУП|ФГБУ|ГБУ|МБУ|АУ|БУ|КУ|ИП|ФБУ|'
    r'общество|акционерное|публичное|с\s+ограниченной\s+ответственностью|'
    r'муниципальное|государственное|унитарное|предприятие|федеральное|'
    r'бюджетное|учреждение)\b', re.I)


def ядро_имени(имя):
    """«АО "Катавский цемент"» → «Катавский цемент»."""
    т = _ФОРМЫ.sub(' ', имя or '')
    т = re.sub(r'["«»\'`]', ' ', т)
    return re.sub(r'\s+', ' ', т).strip(' .,;-')


def _текст(html):
    return re.sub(r'[ \t\u00a0]+', ' ',
                  _ТЕГИ.sub(' ', EC.без_графики(html or '')))


def main():
    db = EDB.EnrichDB()
    q = db.cx.execute
    сп = ','.join('?' * len(ТЕХ))
    с_тел = {r[0] for r in q('SELECT DISTINCT inn FROM phone_contacts')}
    цели = []
    for инн, имя, кратк, сайт, канд in q(
            f"SELECT DISTINCT c.inn,COALESCE(c.name,''),"
            f"COALESCE(c.short_name,''),COALESCE(c.site,''),"
            f"COALESCE(c.cand_site,'') FROM companies c JOIN people p "
            f"ON p.inn=c.inn WHERE p.role IN ({сп})", tuple(ТЕХ)):
        if инн in с_тел:
            continue
        дом = сайт.strip() or канд.strip()
        if not дом:
            continue
        цели.append((инн, (кратк.strip() or имя), дом,
                     'подтверждён' if сайт.strip() else 'кандидат'))

    пройдены = set()
    if os.path.exists(ЖУРНАЛ):
        for ln in io.open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
            try:
                пройдены.add(json.loads(ln).get('инн'))
            except Exception:  # noqa: BLE001
                continue
    работа = [ц for ц in цели if ц[0] not in пройдены][:ЛИМ]
    print(f'предприятий с людьми, без номера и с каким-нибудь доменом: '
          f'{len(цели)}; пройдено ранее: {len(пройдены)}; '
          f'в работу: {len(работа)}; '
          f'режим: {"ПРИМЕНЕНИЕ" if ПРИМЕНИТЬ else "сухой"}', flush=True)
    if not работа:
        print('добирать нечего')
        return

    было = q('SELECT COUNT(*) FROM phone_contacts').fetchone()[0]
    начало = time.time()
    итог = Counter()
    находки = []

    def _журнал(з):
        with open(ЖУРНАЛ, 'a', encoding='utf-8') as ж:
            ж.write(json.dumps(з, ensure_ascii=False) + '\n')
            ж.flush()
            os.fsync(ж.fileno())

    def одно(ц):
        инн, имя, дом, вид = ц
        if time.time() - начало > БЮДЖЕТ:
            return
        осн = дом if дом.startswith('http') else 'http://' + дом
        осн = осн.rstrip('/')
        д = EC.site_domain(осн)
        try:
            h0, _m, _t = EC._fetch_site(осн)
        except Exception:  # noqa: BLE001
            h0 = ''
        if not h0:
            with _ЗАМОК:
                итог['сайт не открылся'] += 1
                _журнал({'инн': инн, 'итог': 'сайт не открылся'})
            return
        страницы = [(осн + '/', h0)]
        видели = set()
        for адрес, текст in _ССЫЛКА.findall(EC.без_графики(h0)):
            подпись = _ТЕГИ.sub(' ', текст)
            if not (_ПОХОЖЕ.search(подпись) or _ПОХОЖЕ.search(адрес)):
                continue
            полн = urllib.parse.urljoin(осн + '/', адрес.strip())
            if EC.site_domain(полн) != д or полн in видели:
                continue
            видели.add(полн)
            if len(видели) >= 18:
                break
        for у in видели:
            if time.time() - начало > БЮДЖЕТ:
                break
            try:
                h, _m, _t = EC._fetch_site(у)
            except Exception:  # noqa: BLE001
                continue
            if h:
                страницы.append((у, h))

        я = ядро_имени(имя)
        варианты = [в for в in {имя.strip(), я} if len(в) >= 5]
        нашли = None
        for у, h in страницы:
            т = _текст(h)
            for в in варианты:
                м = re.search(r'(?<![А-Яа-яЁёA-Za-z])' + re.escape(в)
                              + r'(?![А-Яа-яЁёA-Za-z])', т, re.I)
                if not м:
                    continue
                кусок = т[max(0, м.start() - _ОКНО):м.start() + _ОКНО]
                номера = [x.group(0) for x in EC.phones_in(кусок) if x]
                if номера:
                    нашли = {'номер': номера[0], 'url': у, 'по_имени': в,
                             'кусок': кусок[:160]}
                    break
            if нашли:
                break
        with _ЗАМОК:
            итог['обойдено'] += 1
            итог['страниц'] += len(страницы)
            итог[f'домен: {вид}'] += 1
            if нашли:
                итог['номер найден'] += 1
                находки.append(dict(нашли, инн=инн, имя=имя[:60], вид=вид))
            _журнал({'инн': инн, 'имя': имя[:60], 'вид_домена': вид,
                     'страниц': len(страницы), 'находка': нашли,
                     'итог': 'есть' if нашли else 'названия рядом с номером нет'})

    with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
        list(пул.map(одно, работа))

    if ПРИМЕНИТЬ:
        for н in находки:
            # БЕЗ person: это номер организации, выдавать его за чей-то личный
            # нельзя. Роль тоже не ставим — она относится к человеку.
            db.add_phone(н['инн'], н['номер'],
                         source='сайт: номер рядом с названием предприятия',
                         source_url=н['url'])
        db.cx.commit()

    стало = q('SELECT COUNT(*) FROM phone_contacts').fetchone()[0]
    в_базе = q("SELECT COUNT(*) FROM phone_contacts "
               "WHERE source='сайт: номер рядом с названием предприятия'"
               ).fetchone()[0]
    print()
    print('=== ИЗ БАЗЫ (не из счётчиков прогона) ===')
    print(f'  телефонов: было {было} → стало {стало} (+{стало - было})')
    print(f'  строк этого источника в базе: {в_базе}')
    for к, n in итог.most_common():
        print(f'    {n:>5}  {к}')
    for н in находки[:10]:
        print(f'  {н["имя"]} — {н["номер"]} — по «{н["по_имени"]}» — '
              f'{н["url"][:64]}')


if __name__ == '__main__':
    main()
