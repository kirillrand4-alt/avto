# -*- coding: utf-8 -*-
"""Разведка ЕРКНМ, третий слой: суточный архив весит 338 МБ — качаем на диск.

Что уже известно. Помесячный XML — манифест, в нём 257 суточных версий одного и
того же месяца, и каждая версия — ПОЛНЫЙ архив за месяц, а не дельта. Последняя
версия июня 2026 весит 338 137 846 байт. Первая попытка читала 200 МБ в память
и получила «File is not a zip file» — это не битый архив, это обрезанный.

Отсюда правило для канала: качать РОВНО ОДНУ версию на месяц, последнюю, на
диск, читать потоком и сразу удалять. В память такой файл не берём.

Замеряем то же, ради чего всё затевалось: **есть ли в записях текст, где люди
названы с должностями.** Если нет — канал не даёт ничего, и это надо сказать
прямо, а не после закачки шестидесяти месяцев.

Запуск: python _probe_erknm_zip2.py [ГОД МЕСЯЦ]
"""
import os
import re
import sys
import time
import zipfile

ГОД = sys.argv[1] if len(sys.argv) > 1 else '2026'
МЕС = sys.argv[2] if len(sys.argv) > 2 else '6'
МАНИФЕСТ = ('https://proverki.gov.ru/blob/erknm-opendata/'
            f'7710146102-inspection-{ГОД}-{МЕС}.xml')
ВРЕМЕНКА = r'C:\seostat\drop\_erknm_tmp.zip'
ЧИТАТЬ = 40_000_000        # сколько разжатого текста хватит для замера формы


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


def скачать(url, PX, путь):
    import requests
    for i, px in enumerate(PX[:10]):
        t0 = time.time()
        try:
            r = requests.get(url, proxies={'http': px, 'https': px}, timeout=120,
                             stream=True, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code >= 400:
                print(f'  прокси #{i}: код {r.status_code}')
                continue
            всего = 0
            with open(путь, 'wb') as ф:
                for кусок in r.iter_content(1 << 20):
                    ф.write(кусок)
                    всего += len(кусок)
            r.close()
            print(f'скачано {всего} б за {time.time() - t0:.0f} с '
                  f'(прокси #{i}, {всего / max(1, time.time() - t0) / 1e6:.1f} МБ/с)')
            return всего
        except Exception as e:  # noqa: BLE001
            print(f'  прокси #{i}: {str(e)[:80]}')
    return 0


def main():
    PX = прокси()
    import requests
    ман = None
    for px in PX[:8]:
        try:
            ман = requests.get(МАНИФЕСТ, proxies={'http': px, 'https': px},
                               timeout=60,
                               headers={'User-Agent': 'Mozilla/5.0'}).text
            break
        except Exception:  # noqa: BLE001
            continue
    if not ман:
        print('манифест не открылся')
        return
    ссылки = re.findall(r'<source>([^<]+)</source>', ман)
    print(f'версий за месяц: {len(ссылки)}; берём последнюю')
    if not ссылки:
        return
    if not скачать(ссылки[-1], PX, ВРЕМЕНКА):
        return
    try:
        z = zipfile.ZipFile(ВРЕМЕНКА)
        имена = z.namelist()
        print('внутри файлов:', len(имена), имена[:5])
        with z.open(имена[0]) as ф:
            сырое = ф.read(ЧИТАТЬ)
        print(f'разжато {len(сырое)} б из {имена[0]}')
        текст = сырое.decode('utf-8', 'replace')
        теги = {}
        for т in re.findall(r'<([A-Za-zА-Яа-я_][\w:.-]*)[ />]', текст):
            теги[т] = теги.get(т, 0) + 1
        print('\nчастые теги:', sorted(теги.items(), key=lambda x: -x[1])[:32])
        м = re.search(r'<(inspection|knm|мероприятие|item|erknm)[ >].{300,9000}?</\1>',
                      текст, re.S)
        print('\n--- пример записи ---')
        print((м.group(0)[:4500] if м else текст[:3500]))
        print('\nразных ИНН:',
              len(set(re.findall(r'(?<!\d)(\d{10}|\d{12})(?!\d)', текст))))
        низ = текст.lower()
        for слово in ('энергетик', 'механик', 'главный инженер', 'предостережен',
                      'ответственн', 'должност', 'нарушен', 'фамили'):
            print(f'  «{слово}»: {низ.count(слово)}')
    finally:
        try:
            os.remove(ВРЕМЕНКА)
            print('\nвременный архив удалён')
        except OSError:
            pass


if __name__ == '__main__':
    main()
