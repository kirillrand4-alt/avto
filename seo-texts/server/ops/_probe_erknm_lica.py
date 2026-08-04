# -*- coding: utf-8 -*-
"""Почему сборщик ЕРКНМ дал 193 предприятия и НОЛЬ имён — разбор нуля.

Не спешу объявлять «в ЕРКНМ имён нет». Ровно этот класс ошибки мы ловим третий
раз за смену: отказ разбора, прочитанный как свойство источника. Возможных
причин три, и они различаются:
  1. тексты предостережений лежат НЕ внутри `INSPECTION`, а отдельным типом
     записи — тогда мой обход их не видел вовсе;
  2. текст есть, но лежит в АТРИБУТЕ, которого нет в моём списке
     (VALUE/CAPTION/CONTENT/NAME);
  3. текст есть и прочитан, но моё выражение для «должность + ФИО» слишком
     строгое.
Различаю их так: печатаю все корневые типы записей, показываю сырой кусок
`WARNING_INFO` целиком и отдельно прогоняю по нему выражение.

КЭШИРУЕТ АРХИВ. Скачивание 338 МБ занимает ~9 минут; повторять его на каждую
догадку — расточительство. Файл остаётся на диске, следующий запуск его берёт.

Запуск: python _probe_erknm_lica.py [ГОД МЕСЯЦ] [--udalit]
"""
import os
import re
import sys
import zipfile
from collections import Counter

ГОД = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('-') else '2026'
МЕС = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('-') else '6'
КЭШ = fr'C:\seostat\drop\_erknm_{ГОД}_{МЕС}.zip'
ЧИТАТЬ = 90_000_000


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


def добыть():
    if os.path.exists(КЭШ) and os.path.getsize(КЭШ) > 10_000_000:
        print('архив уже на диске:', os.path.getsize(КЭШ), 'б')
        return True
    import requests
    PX = прокси()
    ман = None
    урл = ('https://proverki.gov.ru/blob/erknm-opendata/'
           f'7710146102-inspection-{ГОД}-{МЕС}.xml')
    for px in PX[:8]:
        try:
            ман = requests.get(урл, proxies={'http': px, 'https': px},
                               timeout=60, headers={'User-Agent': 'Mozilla/5.0'}).text
            break
        except Exception:  # noqa: BLE001
            continue
    ссылки = re.findall(r'<source>([^<]+)</source>', ман or '')
    if not ссылки:
        print('манифест не открылся')
        return False
    for i, px in enumerate(PX[:10]):
        try:
            r = requests.get(ссылки[-1], proxies={'http': px, 'https': px},
                             timeout=120, stream=True,
                             headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code >= 400:
                continue
            с = 0
            with open(КЭШ, 'wb') as ф:
                for к in r.iter_content(1 << 20):
                    ф.write(к)
                    с += len(к)
            r.close()
            print(f'скачано {с} б (прокси #{i})')
            return True
        except Exception as e:  # noqa: BLE001
            print(f'  прокси #{i}: {str(e)[:70]}')
    return False


ТЕХ = ('энергетик', 'механик', 'главный инженер', 'технический директор',
       'начальник цеха', 'начальник участка', 'начальник службы',
       'начальник отдела', 'инженер', 'ответственн', 'мастер')
СТРОГО = re.compile(
    r'(?P<d>(?:[а-яё]+[\s-]+){0,3}(?:' + '|'.join(ТЕХ) + r')[а-яё\s]{0,26}?)'
    r'[\s—-]+(?P<f>[А-ЯЁ][а-яё]{2,}\s+'
    r'(?:[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}|[А-ЯЁ]\.\s?[А-ЯЁ]\.))')
# мягкое: ФИО и должность в ЛЮБОМ порядке и на расстоянии до 60 знаков
МЯГКО = re.compile(
    r'(?:(?P<d1>' + '|'.join(ТЕХ) + r')[^.;]{0,60}?'
    r'(?P<f1>[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}))'
    r'|(?:(?P<f2>[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,})'
    r'[^.;]{0,60}?(?P<d2>' + '|'.join(ТЕХ) + r'))')


def main():
    if not добыть():
        return
    z = zipfile.ZipFile(КЭШ)
    имя = z.namelist()[0]
    with z.open(имя) as ф:
        текст = ф.read(ЧИТАТЬ).decode('utf-8', 'replace')
    print(f'разжато {len(текст)} б')

    корни = Counter(re.findall(r'<(?:ns\d+:)?([A-Z_]{4,})[ >]', текст))
    print('\nтипы записей (верх):', корни.most_common(20))

    # WARNING_INFO целиком, как оно есть в файле
    примеры = re.findall(r'<WARNING_INFO.{0,2500}?</WARNING_INFO>', текст, re.S)
    print(f'\nблоков WARNING_INFO в куске: {len(примеры)}')
    for п in примеры[:2]:
        print('--- сырой блок ---')
        print(п[:2000])

    # где вообще встречаются технические слова
    print('\nконтекст технических слов (первые 6):')
    показано = 0
    for м in re.finditer('|'.join(ТЕХ), текст):
        а, б = max(0, м.start() - 160), м.end() + 160
        кусок = re.sub(r'\s+', ' ', текст[а:б])
        print('  …', кусок)
        показано += 1
        if показано >= 6:
            break

    только = ' '.join(re.sub(r'<[^>]+>', ' ', п) for п in примеры)
    print(f'\nтекста предостережений: {len(только)} знаков')
    с = len(set(m.group('f') for m in СТРОГО.finditer(только)))
    мяг = set()
    for m in МЯГКО.finditer(только):
        мяг.add(m.group('f1') or m.group('f2'))
    print(f'строгое выражение нашло имён: {с}')
    print(f'мягкое выражение нашло имён: {len(мяг)}')
    for и in list(мяг)[:12]:
        print('   ', и)

    if '--udalit' in sys.argv:
        os.remove(КЭШ)
        print('кэш удалён')


if __name__ == '__main__':
    main()
