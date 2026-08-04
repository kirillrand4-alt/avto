# -*- coding: utf-8 -*-
"""Разведка второго слоя ЕРКНМ: помесячный XML — это МАНИФЕСТ, данные в ZIP.

Что выяснилось на первом шаге: `7710146102-inspection-2026-6.xml` весит 71 КБ и
не содержит ни одной проверки — это перечень суточных архивов вида
`/blob/erknm-opendata/<год>/<месяц>/data-<ГГГГММДД>-structure-20220125.zip`.
Значит тянуть надо ZIP, а XML читать только ради списка ссылок.

Замеряем ровно три вещи, прежде чем строить канал:
1. вес архива (от него зависит, сколько суток реально скачать);
2. что внутри — одна запись на проверку или пачка;
3. **есть ли в записи текст, где названы люди с должностями.** Если имён нет —
   канал не даёт ничего, и честнее сказать это сразу, чем качать 60 месяцев.

Ничего не пишет. Запуск: python _probe_erknm_zip.py [ГОД МЕСЯЦ]
"""
import io
import os
import re
import sys
import zipfile

ГОД = sys.argv[1] if len(sys.argv) > 1 else '2026'
МЕС = sys.argv[2] if len(sys.argv) > 2 else '6'
МАНИФЕСТ = ('https://proverki.gov.ru/blob/erknm-opendata/'
            f'7710146102-inspection-{ГОД}-{МЕС}.xml')


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


def тянуть(url, PX, лимит=None):
    import requests
    зг = {'User-Agent': 'Mozilla/5.0', 'Accept': '*/*'}
    if лимит:
        зг['Range'] = f'bytes=0-{лимит}'
    for i, px in enumerate(PX[:12]):
        try:
            r = requests.get(url, proxies={'http': px, 'https': px}, timeout=60,
                             stream=True, headers=зг)
            if r.status_code >= 400:
                print(f'  прокси #{i}: код {r.status_code}')
                continue
            дл = r.headers.get('Content-Length')
            тело = r.raw.read(лимит or 200_000_000, decode_content=True)
            r.close()
            return тело, дл
        except Exception as e:  # noqa: BLE001
            print(f'  прокси #{i}: {str(e)[:80]}')
    return None, None


def main():
    PX = прокси()
    ман, _ = тянуть(МАНИФЕСТ, PX, лимит=3_000_000)
    if not ман:
        print('манифест не открылся')
        return
    ссылки = re.findall(r'<source>([^<]+)</source>', ман.decode('utf-8', 'replace'))
    print(f'суточных архивов в манифесте: {len(ссылки)}')
    if not ссылки:
        return
    зип_урл = ссылки[-1]
    print('берём последний:', зип_урл)
    тело, дл = тянуть(зип_урл, PX)
    if not тело:
        print('архив не открылся')
        return
    print(f'скачано {len(тело)} б (Content-Length={дл})')
    try:
        z = zipfile.ZipFile(io.BytesIO(тело))
    except Exception as e:  # noqa: BLE001
        print('не распаковался:', str(e)[:120], '| первые байты:', тело[:40])
        return
    имена = z.namelist()
    print('файлов внутри:', len(имена), имена[:6])
    сырое = z.read(имена[0])
    print(f'первый файл {имена[0]}: {len(сырое)} б')
    текст = сырое.decode('utf-8', 'replace')
    теги = {}
    for т in re.findall(r'<([A-Za-zА-Яа-я_][\w:.-]*)[ />]', текст):
        теги[т] = теги.get(т, 0) + 1
    print('\nчастые теги:', sorted(теги.items(), key=lambda x: -x[1])[:30])
    м = re.search(r'<(inspection|knm|мероприятие|item)[ >].{300,8000}?</\1>',
                  текст, re.S)
    print('\n--- пример записи ---')
    print((м.group(0)[:4000] if м else текст[:3000]))
    print('\nразных ИНН в файле:',
          len(set(re.findall(r'(?<!\d)(\d{10}|\d{12})(?!\d)', текст))))
    низ = текст.lower()
    for слово in ('энергетик', 'механик', 'главный инженер', 'предостережен',
                  'ответственн', 'должност', 'фио', 'нарушен'):
        print(f'  «{слово}»: {низ.count(слово)}')


if __name__ == '__main__':
    main()
