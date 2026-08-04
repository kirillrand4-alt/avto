# -*- coding: utf-8 -*-
"""ЕРКНМ как канал: суточный архив надзора → наши предприятия → имена и роли.

ЧТО ЭТО ЗА ИСТОЧНИК И ПОЧЕМУ ОН ВЗЯТ ТАК. Поиск на сайте требует капчу на
каждый запрос, а открытые данные — нет. Форма выгрузки:
    манифест   /blob/erknm-opendata/7710146102-inspection-<год>-<мес>.xml
    в нём 257 суточных версий ОДНОГО И ТОГО ЖЕ месяца, каждая — полный срез;
    берём ПОСЛЕДНЮЮ: .../<год>/<мес>/data-<ГГГГММДД>-structure-20220125.zip
Вес одной версии — 338 МБ (июнь 2026), качается за ~9 минут через socks5;
серверный адрес площадку не видит вовсе, нужен прокси.

ЧТО ВНУТРИ, ПРОВЕРЕНО НА ПЕРВЫХ 40 МБ. Записи `INSPECTION` с `SUBJECT INN`,
и в них два разных сорта людей, которые НЕЛЬЗЯ путать:
  * `INSPECTOR_FULL_NAME` — проверяющий ОТ НАДЗОРА (Роспотребнадзор и т.п.).
    Нам он не нужен вообще: это не сотрудник предприятия;
  * текст `WARNING_CONTENT` (предостережения, 1438 штук на 40 МБ) — вот там
    называют работников предприятия с должностями.
Поэтому имена берём ТОЛЬКО из текстов, а `INSPECTOR` явно пропускаем. Без этого
различения канал выдал бы нам сотни инспекторов вместо технических ЛПР.

ОГРАНИЧЕНИЕ ВЛАДЕЛЬЦА: «1573 = не надо, надо только те которые отображаются в
базе». Цели — из `erknm-celi.csv` (видимые и без техчеловека), их 385.

ПРАВИЛО, КОТОРОЕ НЕЛЬЗЯ НАРУШАТЬ (2-я сессия, я согласен): **повод для звонка
отсюда брать НЕЛЬЗЯ.** Человека назвали в предостережении потому, что он НЕ
ПРОШЁЛ проверку знаний. Берём «кто занимает роль», повод — из состояния машины.

ДОЛГОВЕЧНОСТЬ. Каждое найденное предприятие пишется строкой в серверный поток
`C:\\seostat\\drop\\erknm_stream.jsonl` с fsync сразу. Разобранные месяцы
отмечаются там же, поэтому перезапуск не качает заново то, что уже прошло.

Запуск: python erknm_sbor.py --god 2026 --mes 6 [--vse]
"""
import io
import json
import os
import re
import sys
import time
import zipfile
from collections import Counter
from xml.etree import ElementTree as ET

ПОТОК = r'C:\seostat\drop\erknm_stream.jsonl'
ЦЕЛИ = os.path.join(r'C:\seostat\drop\drop-storage', 'erknm-celi.csv')
ВРЕМЕНКА = r'C:\seostat\drop\_erknm_tmp.zip'


def арг(имя, поум=None):
    try:
        return sys.argv[sys.argv.index(имя) + 1]
    except (ValueError, IndexError):
        return поум


ГОД = арг('--god', '2026')
МЕС = арг('--mes', '6')
ВСЕ = '--vse' in sys.argv          # брать все предприятия, а не только цели

ТЕХ = ('энергетик', 'механик', 'главный инженер', 'технический директор',
       'начальник цеха', 'начальник участка', 'начальник службы',
       'начальник отдела', 'инженер', 'ответственн', 'мастер')
ЛИЦО = re.compile(
    r'(?P<dolzh>(?:[а-яё]+[\s-]+){0,3}(?:' + '|'.join(ТЕХ) + r')[а-яё\s]{0,26}?)'
    r'[\s—-]+(?P<fio>[А-ЯЁ][а-яё]{2,}\s+'
    r'(?:[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}|[А-ЯЁ]\.\s?[А-ЯЁ]\.))')


def лица_из_текста(текст):
    """Имя + должность из текста надзорного документа. Сам текст не храним."""
    найдено = {}
    for м in ЛИЦО.finditer(re.sub(r'\s+', ' ', текст or '')):
        долж = м.group('dolzh').strip(' ,;:.—-').lower()
        фио = re.sub(r'\s+', ' ', м.group('fio')).strip()
        if len(фио.split()) < 2 or not any(к in долж for к in ТЕХ):
            continue
        найдено.setdefault(фио, долж[:80])
    return [{'chelovek': ф, 'dolzhnost': д} for ф, д in найдено.items()]


def цели():
    import csv
    csv.field_size_limit(10 ** 7)
    из = {}
    if os.path.exists(ЦЕЛИ):
        with open(ЦЕЛИ, encoding='utf-8-sig', errors='replace', newline='') as ф:
            for r in csv.DictReader(ф, delimiter=';'):
                и = re.sub(r'\D', '', str(r.get('inn') or ''))
                if len(и) in (10, 12):
                    из[и] = str(r.get('name') or '')
    return из


def прокси():
    import urllib.request
    d = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    зпр = urllib.request.Request(
        os.environ.get('DROP_URL', '').rstrip('/') + '/dolphin-proxies.txt',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    из = []
    for l in d.open(зпр, timeout=30).read().decode('utf-8', 'replace').splitlines():
        l = l.strip()
        m = (re.match(r'(?:([^:@]+):([^@]*)@)?([^:/]+):(\d+)', l)
             if l and not l.startswith('#') else None)
        if m:
            u, pw, h, _ = m.groups()
            из.append('socks5://%s:%s@%s:3001' % (u, pw, h))
    return из


def записать(запись):
    with open(ПОТОК, 'a', encoding='utf-8') as ф:
        ф.write(json.dumps(запись, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())


def месяц_пройден(год, мес):
    if not os.path.exists(ПОТОК):
        return False
    метка = f'{год}-{мес}'
    for стр in open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(стр)
        except Exception:  # noqa: BLE001
            continue
        if з.get('vid') == 'месяц-закрыт' and з.get('mesyac') == метка:
            return True
    return False


def скачать(url, PX, путь):
    import requests
    for i, px in enumerate(PX[:10]):
        t0 = time.time()
        try:
            r = requests.get(url, proxies={'http': px, 'https': px}, timeout=120,
                             stream=True, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code >= 400:
                continue
            всего = 0
            with open(путь, 'wb') as ф:
                for кусок in r.iter_content(1 << 20):
                    ф.write(кусок)
                    всего += len(кусок)
            r.close()
            print(f'скачано {всего} б за {time.time() - t0:.0f} с (прокси #{i})',
                  flush=True)
            return всего
        except Exception as e:  # noqa: BLE001
            print(f'  прокси #{i}: {str(e)[:70]}', flush=True)
    return 0


def текст_записи(эл):
    """Все тексты предостережений и решений записи — БЕЗ имён инспекторов.

    INSPECTOR выкидывается целиком: там сотрудники надзора, а не предприятия.
    Их попадание в выход и было бы главной ошибкой этого канала.
    """
    куски = []
    for под in эл.iter():
        имя = под.tag.rsplit('}', 1)[-1]
        if имя.startswith('INSPECTOR'):
            continue
        if под.text and под.text.strip():
            куски.append(под.text.strip())
        for к, v in под.attrib.items():
            if к in ('VALUE', 'CAPTION', 'CONTENT', 'NAME') and len(str(v)) > 25:
                куски.append(str(v))
    return ' '.join(куски)


def main():
    if месяц_пройден(ГОД, МЕС):
        print(f'месяц {ГОД}-{МЕС} уже разобран — пропуск')
        return
    цел = цели()
    print(f'целей в списке: {len(цел)}'
          + ('  (режим --vse: фильтр по целям выключен)' if ВСЕ else ''))
    PX = прокси()
    import requests
    манифест = ('https://proverki.gov.ru/blob/erknm-opendata/'
                f'7710146102-inspection-{ГОД}-{МЕС}.xml')
    ман = None
    for px in PX[:8]:
        try:
            ман = requests.get(манифест, proxies={'http': px, 'https': px},
                               timeout=60,
                               headers={'User-Agent': 'Mozilla/5.0'}).text
            break
        except Exception:  # noqa: BLE001
            continue
    ссылки = re.findall(r'<source>([^<]+)</source>', ман or '')
    if not ссылки:
        print('манифест пуст или не открылся')
        return
    print(f'версий за месяц {len(ссылки)}, берём последнюю', flush=True)
    if not скачать(ссылки[-1], PX, ВРЕМЕНКА):
        print('архив не скачался')
        return

    стат = Counter()
    найдено_по_инн = {}
    try:
        z = zipfile.ZipFile(ВРЕМЕНКА)
        имя_вн = z.namelist()[0]
        with z.open(имя_вн) as поток:
            for событие, эл in ET.iterparse(io.BufferedReader(поток, 1 << 20),
                                            events=('end',)):
                if not эл.tag.endswith('INSPECTION'):
                    continue
                стат['записей прочитано'] += 1
                инн = ''
                for под in эл:
                    if под.tag.endswith('SUBJECT'):
                        инн = re.sub(r'\D', '', под.get('INN') or '')
                        break
                if инн and (ВСЕ or инн in цел):
                    стат['ЗАПИСЕЙ ПО НАШИМ'] += 1
                    т = текст_записи(эл)
                    лица = лица_из_текста(т)
                    з = найдено_по_инн.setdefault(
                        инн, {'inn': инн, 'name': цел.get(инн, ''),
                              'meropriyatiy': 0, 'lica': [], 'daty': []})
                    з['meropriyatiy'] += 1
                    д = эл.get('START_DATE') or ''
                    if д and д not in з['daty']:
                        з['daty'].append(д)
                    видел = {л['chelovek'] for л in з['lica']}
                    for л in лица:
                        if л['chelovek'] not in видел:
                            л['erpid'] = эл.get('ERPID') or ''
                            л['data'] = д
                            з['lica'].append(л)
                            видел.add(л['chelovek'])
                эл.clear()
                if стат['записей прочитано'] % 50000 == 0:
                    print(f'  прочитано {стат["записей прочитано"]}, '
                          f'наших {стат["ЗАПИСЕЙ ПО НАШИМ"]}', flush=True)
    finally:
        try:
            os.remove(ВРЕМЕНКА)
        except OSError:
            pass

    лиц = 0
    for з in найдено_по_инн.values():
        з['mesyac'] = f'{ГОД}-{МЕС}'
        з['vid'] = 'предприятие'
        з['ts'] = int(time.time())
        лиц += len(з['lica'])
        записать(з)
    записать({'vid': 'месяц-закрыт', 'mesyac': f'{ГОД}-{МЕС}',
              'ts': int(time.time()),
              'zapisey': стат['записей прочитано'],
              'nashih': стат['ЗАПИСЕЙ ПО НАШИМ'],
              'predpriyatiy': len(найдено_по_инн), 'lic': лиц})
    print(json.dumps({'записей в архиве': стат['записей прочитано'],
                      'записей по нашим предприятиям': стат['ЗАПИСЕЙ ПО НАШИМ'],
                      'предприятий найдено': len(найдено_по_инн),
                      'ЛИЦ ИЗВЛЕЧЕНО': лиц}, ensure_ascii=False, indent=1))
    for з in list(найдено_по_инн.values())[:10]:
        if з['lica']:
            print(f"  {з['inn']} {з['name'][:34]:34} "
                  + '; '.join(f"{л['dolzhnost'][:22]}: {л['chelovek']}"
                              for л in з['lica'][:3]))


if __name__ == '__main__':
    main()
