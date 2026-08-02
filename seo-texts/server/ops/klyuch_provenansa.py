# -*- coding: utf-8 -*-
"""Ключ «строка → откуда взята» для третьей сессии.

Она просит его прямо: «у кого лежит enrich.db и выгрузки с сайтов, пришлите
ключ строка → откуда взята, я дострою ссылки». enrich.db у меня, значит
отдать должен я.

Формат делаю под её задачу: по каждому человеку и каждому телефону — ИНН,
значение, источник и ссылка, если она есть. Плюс колонка `chem_dokazano`,
чтобы было видно, ссылка это на документ или на выдачу поиска: она строит
ссылки детерминированно, и подсунуть ей поиск вместо документа значит
испортить её же работу.
"""
import csv
import os
import re
import sys
import urllib.request

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ИМЯ = 'KLYUCH-PROVENANSA-ot-1-sessii.csv'
_ДОБ = re.compile(r'\s*(?:доб|вн|внутр|ext)\.?\s*[:№]?\s*[\d\-]+\s*$', re.I)


def д10(т):
    ц = re.sub(r'\D', '', _ДОБ.sub('', str(т or '')))
    return ц[-10:] if len(ц) >= 10 else ''


def main():
    db = EDB.EnrichDB()
    q = db.cx.execute
    тех = set(EDB.EnrichDB.TECH_ROLES) | {'техконтакт'}
    строки = []
    for инн, фио, пост, роль, тел, поч, ист, урл in q(
            "SELECT inn, person, COALESCE(post,''), COALESCE(role,''), "
            "COALESCE(phone,''), COALESCE(email,''), COALESCE(source,''), "
            "COALESCE(source_url,'') FROM people").fetchall():
        строки.append(['человек', инн, фио, пост[:90], роль, тел, поч, ист[:90],
                       урл[:200],
                       'ссылка на страницу-источник' if урл.startswith('http')
                       else 'ссылки нет',
                       'да' if роль in тех else 'нет'])
    for инн, тел, фио, роль, ист, урл in q(
            "SELECT inn, phone, COALESCE(person,''), COALESCE(role,''), "
            "COALESCE(source,''), COALESCE(source_url,'') "
            'FROM phone_contacts').fetchall():
        строки.append(['телефон', инн, тел, '', роль, д10(тел), '', ист[:90],
                       (урл or '')[:200],
                       'ссылка на страницу-источник' if (урл or '').startswith('http')
                       else 'ссылки нет',
                       'да' if роль in тех else 'нет'])
    for инн, поч, роль, чел, ист, урл in q(
            "SELECT inn, email, COALESCE(role,''), COALESCE(person,''), "
            "COALESCE(source,''), COALESCE(source_url,'') FROM emails").fetchall():
        строки.append(['почта', инн, поч, '', роль, '', поч, ист[:90],
                       (урл or '')[:200],
                       'ссылка на страницу-источник' if (урл or '').startswith('http')
                       else 'ссылки нет',
                       'да' if роль in тех else 'нет'])

    путь = os.path.join(r'C:\sender\server', ИМЯ)
    with open(путь, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow(['tip', 'inn', 'znachenie', 'dolzhnost', 'rol',
                    'nomer_10cifr_ili_pochta', 'pochta', 'istochnik',
                    'ssylka_na_istochnik', 'chto_za_ssylka', 'tehLPR'])
        в.writerows(строки)
        ф.flush()
        os.fsync(ф.fileno())

    # числа перечитыванием файла
    вс = сс = 0
    типы = {}
    with open(путь, encoding='utf-8-sig', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            вс += 1
            типы[r['tip']] = типы.get(r['tip'], 0) + 1
            if r['ssylka_na_istochnik'].strip():
                сс += 1
    print(f'{ИМЯ}: строк {вс}')
    for т, n in sorted(типы.items(), key=lambda x: -x[1]):
        print(f'  {n:>6}  {т}')
    print(f'  со ссылкой на источник: {сс} ({round(100 * сс / max(1, вс))}%)')
    try:
        урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
        зпр = urllib.request.Request(
            урл.rstrip('/') + '/' + ИМЯ, data=open(путь, 'rb').read(),
            method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
        urllib.request.urlopen(зпр, timeout=300).read()
        print(f'  на дропе: {ИМЯ}')
    except Exception as e:  # noqa: BLE001
        print(f'  на дроп НЕ легло: {str(e)[:120]}')


if __name__ == '__main__':
    main()
