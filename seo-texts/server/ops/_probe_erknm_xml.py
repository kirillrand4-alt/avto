# -*- coding: utf-8 -*-
"""Разведка помесячных выгрузок ЕРКНМ: размер, поля, есть ли имена в текстах.

Дешёвый замер ПЕРЕД тем, как строить канал. Проверяем три вещи:
1. открывается ли blob с наших socks5 (серверный адрес площадку не видит вовсе);
2. сколько весит месяц — от этого зависит, тянуть ли все 60+ месяцев;
3. есть ли в записи ИНН и текст, где названы люди с должностями.

Ничего не пишет в базы. Запуск: python _probe_erknm_xml.py [ГОД МЕСЯЦ]
"""
import os
import re
import sys
import time
import urllib.request

ШАБЛОН = ('https://proverki.gov.ru/blob/erknm-opendata/'
          '7710146102-inspection-{}-{}.xml')
ГОД = sys.argv[1] if len(sys.argv) > 1 else '2026'
МЕС = sys.argv[2] if len(sys.argv) > 2 else '6'
КУСОК = 900_000          # первые ~0,9 МБ хватит, чтобы увидеть форму записи


def прокси():
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


def main():
    url = ШАБЛОН.format(ГОД, МЕС)
    print('пробуем', url)
    PX = прокси()
    print('прокси в списке:', len(PX))
    данные = None
    # ВАЖНО: socks5 умеет requests+PySocks, а urllib НЕ умеет — он открывает
    # сырое соединение и падает на первых байтах рукопожатия («\x00[…»).
    # Именно на этом сломалась первая попытка.
    # Тайм-аут короткий и прокси много: месячная выгрузка может весить сотни
    # мегабайт, и «ждать 90 с на каждом» — это 9 минут на одном лишь переборе.
    # Просим первые 900 КБ через Range, чтобы не тянуть файл целиком ради формы.
    import requests
    for i, px in enumerate(PX[:14]):
        t0 = time.time()
        try:
            r = requests.get(url, proxies={'http': px, 'https': px}, timeout=25,
                             stream=True,
                             headers={'User-Agent': 'Mozilla/5.0', 'Accept': '*/*',
                                      'Range': f'bytes=0-{КУСОК}'})
            размер = r.headers.get('Content-Length')
            данные = r.raw.read(КУСОК, decode_content=True)
            print(f'ok через прокси #{i}: код {r.status_code}, '
                  f'Content-Length={размер}, прочитано {len(данные)} б '
                  f'за {time.time() - t0:.1f} с')
            r.close()
            break
        except Exception as e:  # noqa: BLE001
            print(f'  прокси #{i}: {str(e)[:90]}')
    if not данные:
        print('НЕ ОТКРЫЛОСЬ ни с одного прокси')
        return

    текст = данные.decode('utf-8', 'replace')
    теги = re.findall(r'<([A-Za-zА-Яа-я_][\w:.-]*)[ />]', текст)
    частые = {}
    for т in теги:
        частые[т] = частые.get(т, 0) + 1
    print('\nчастые теги:',
          sorted(частые.items(), key=lambda x: -x[1])[:25])
    м = re.search(r'<(inspection|knm|мероприятие)[ >].{200,6000}?</\1>', текст, re.S)
    print('\n--- пример записи ---')
    print((м.group(0)[:3000] if м else текст[:2500]))
    print('\nИНН в куске:', len(set(re.findall(r'(?<!\d)(\d{10}|\d{12})(?!\d)', текст))))
    for слово in ('энергетик', 'механик', 'главный инженер', 'предостережен',
                  'ответственн', 'должност'):
        print(f'  «{слово}»: {текст.lower().count(слово)}')


if __name__ == '__main__':
    main()
