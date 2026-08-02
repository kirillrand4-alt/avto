# -*- coding: utf-8 -*-
"""Прямой номер известного человека: ищем на сайте ПО ЕГО ФАМИЛИИ.

Обход справочников подразделений искал людей вслепую — брал страницу и
вытаскивал всё, что похоже на «ФИО плюс телефон». Теперь задача другая и
проще: у 724 технических руководителей мы ЗНАЕМ имя (в основном из графиков
Ростехнадзора), не знаем только номер, и у 224 их предприятий есть
подтверждённый сайт. Искать надо не «кого-нибудь», а конкретную фамилию.

Это ловит то, что слепой обход пропускает: человек упомянут в новости, в
разделе «структура», в подписи под документом, в объявлении о приёме — там,
где шаблон «строка справочника» не срабатывает, а фамилия и номер рядом стоят.

Рубежи те же, что и в обходе, и по тем же причинам:
  * `без_графики` ДО любого разбора — inline-SVG даёт «телефоны» из координат;
  * телефоны только через `phones_in`, запись только через `add_phone`
    (там стоит отсев ИНН/ОГРН, принятых за номер);
  * номер берётся ТОЛЬКО из окна вокруг самой фамилии, а не со страницы
    вообще: иначе человеку припишется телефон приёмной, стоящий в подвале;
  * фамилия должна встретиться отдельным словом, а не внутри другого.

Durable: журнал `nomer_po_imeni.jsonl` с flush+fsync. Резюмируемо по журналу.

Запуск: python nomer_po_imeni.py [--lim N] [--potokov N] [--budget СЕК] [--apply]
"""
import io
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB       # noqa: E402
import enrich_contacts as EC  # noqa: E402

ПРИМЕНИТЬ = '--apply' in sys.argv


def арг(имя, поум):
    return sys.argv[sys.argv.index(имя) + 1] if имя in sys.argv else поум


ЛИМ = int(арг('--lim', '120'))
ПОТОКОВ = int(арг('--potokov', '8'))
БЮДЖЕТ = float(арг('--budget', '900'))
ЖУРНАЛ = r'C:\sender\server\nomer_po_imeni.jsonl'
ТЕХ = set(EDB.EnrichDB.TECH_ROLES)
_ЗАМОК = threading.Lock()

# страницы, где человека называют по имени рядом с телефоном
_ПОХОЖЕ = re.compile(
    r'контакт|структур|подразделен|руковод|отдел|служб|телефон|справочник|'
    r'администрац|kontakt|contact|struktur|about|company|staff|team|'
    r'sotrudnik|personal|news|novosti|press', re.I)
_ССЫЛКА = re.compile(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.{0,120}?)</a>',
                     re.I | re.S)
_ТЕГИ = re.compile(r'<[^>]+>')
# добавочный берём только вплотную к номеру — склейка приёмной с чужим «доб.»
# уже стоила сфабрикованного номера
_ОКНО = 260


def _текст(html):
    т = _ТЕГИ.sub(' ', EC.без_графики(html or ''))
    return re.sub(r'[ \t\u00a0]+', ' ', т)


def main():
    db = EDB.EnrichDB()
    q = db.cx.execute
    сп = ','.join('?' * len(ТЕХ))
    цели = defaultdict(list)
    сайты = {}
    for инн, чел, пост, роль, сайт in q(
            f"SELECT p.inn,p.person,COALESCE(p.post,''),p.role,"
            f"COALESCE(c.site,'') FROM people p JOIN companies c "
            f"ON c.inn=p.inn WHERE p.role IN ({сп}) "
            f"AND COALESCE(p.phone,'')='' AND COALESCE(c.site,'')<>''",
            tuple(ТЕХ)):
        цели[инн].append({'фио': чел, 'пост': пост, 'роль': роль})
        сайты[инн] = сайт

    пройдены = set()
    if os.path.exists(ЖУРНАЛ):
        for ln in io.open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
            try:
                пройдены.add(json.loads(ln).get('инн'))
            except Exception:  # noqa: BLE001
                continue
    работа = [и for и in цели if и not in пройдены][:ЛИМ]
    print(f'предприятий с сайтом и безномерными техЛПР: {len(цели)}; '
          f'пройдено ранее: {len(пройдены)}; в работу: {len(работа)}; '
          f'режим: {"ПРИМЕНЕНИЕ" if ПРИМЕНИТЬ else "сухой"}', flush=True)
    if not работа:
        print('искать нечего')
        return

    было = q('SELECT COUNT(*) FROM phone_contacts').fetchone()[0]
    начало = time.time()
    итог = Counter()
    находки = []

    def одно(инн):
        if time.time() - начало > БЮДЖЕТ:
            return
        сайт = сайты[инн]
        осн = сайт if сайт.startswith('http') else 'http://' + сайт
        осн = осн.rstrip('/')
        дом = EC.site_domain(осн)
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
            if EC.site_domain(полн) != дом or полн in видели:
                continue
            видели.add(полн)
            if len(видели) >= 16:
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

        нашли = []
        for чел in цели[инн]:
            фам = (чел['фио'].split() or [''])[0]
            if len(фам) < 4:
                continue
            ре = re.compile(r'(?<![А-Яа-яЁё])' + re.escape(фам) + r'(?![А-Яа-яЁё])')
            for у, h in страницы:
                т = _текст(h)
                м = ре.search(т)
                if not м:
                    continue
                кусок = т[max(0, м.start() - _ОКНО):м.start() + _ОКНО]
                # phones_in отдаёт ОБЪЕКТЫ СОВПАДЕНИЯ, а не строки: без
                # .group(0) в базу уехало бы «<re.Match object …>».
                номера = [m.group(0) for m in EC.phones_in(кусок) if m]
                if not номера:
                    continue
                нашли.append({'фио': чел['фио'], 'пост': чел['пост'],
                              'роль': чел['роль'], 'номер': номера[0],
                              'url': у, 'кусок': кусок[:160]})
                break
        with _ЗАМОК:
            итог['предприятий обойдено'] += 1
            итог['страниц'] += len(страницы)
            if нашли:
                итог['предприятий с находкой'] += 1
                итог['людей с номером'] += len(нашли)
                находки.extend([dict(н, инн=инн) for н in нашли])
            _журнал({'инн': инн, 'страниц': len(страницы),
                     'нашли': len(нашли),
                     'итог': 'есть' if нашли else 'фамилий рядом с номером нет'})

    def _журнал(з):
        with open(ЖУРНАЛ, 'a', encoding='utf-8') as ж:
            ж.write(json.dumps(з, ensure_ascii=False) + '\n')
            ж.flush()
            os.fsync(ж.fileno())

    with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
        list(пул.map(одно, работа))

    if ПРИМЕНИТЬ:
        for н in находки:
            db.add_phone(н['инн'], н['номер'], person=н['фио'], role=н['роль'],
                         source='сайт: номер рядом с фамилией',
                         source_url=н['url'])
        db.cx.commit()

    стало = q('SELECT COUNT(*) FROM phone_contacts').fetchone()[0]
    print()
    print('=== ИЗ БАЗЫ (не из счётчиков прогона) ===')
    print(f'  телефонов: было {было} → стало {стало} (+{стало - было})')
    print('  что происходило:')
    for к, n in итог.most_common():
        print(f'    {n:>5}  {к}')
    for н in находки[:8]:
        print(f'  {н["фио"]} ({н["роль"]}) — {н["номер"]} — {н["url"][:70]}')
    print('ИТОГ ' + json.dumps({'обойдено': len(работа),
                                'людей_с_номером': len(находки),
                                'секунд': round(time.time() - начало)},
                               ensure_ascii=False))


if __name__ == '__main__':
    main()
