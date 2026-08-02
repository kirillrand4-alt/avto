# -*- coding: utf-8 -*-
"""Дошли ли новые контакты ДО САЙТА, который видят продавцы.

Владелец спросил прямо: данные, которые мы достали, добавлены на сайт?
Отвечать надо сверкой двух хранилищ, а не памятью о том, что я куда клал:

  * `centrifugal.db` — база ПАНЕЛИ. Её показывает сайт /obzvon/centro/.
    Она read-only и целиком пересобирается офлайн-скриптом;
  * `enrich.db` + `BAZA-CENTROBEZHNIKI-OBSHCHAYA.csv` — мои. Туда за сегодня
    влиты вложения ЕИС, обход сайтов и Тендер.Про.

Если второе богаче первого — значит продавец наших находок НЕ ВИДИТ, сколько
бы я ни отчитывался про «влито». Это и проверяем: по людям, по телефонам и
пофамильно, а не по общему счёту, потому что общий счёт может сойтись при
полностью разном составе.

Запуск: python sverka_panel_baza.py
"""
import csv
import io
import os
import re
import sys
from collections import Counter

sys.path.insert(0, r'C:\seostat')
sys.path.insert(0, r'C:\sender\server')
from app.services import centro_catalog  # noqa: E402
import enrich_db as EDB  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'
_ДОБ = re.compile(r'\s*(?:доб|вн|внутр|ext)\.?\s*[:№]?\s*[\d\-]+\s*$', re.I)


def клч(т):
    return re.sub(r'\s+', ' ', str(т or '').strip().lower()).replace('ё', 'е')


def д10(т):
    ц = re.sub(r'\D', '', _ДОБ.sub('', str(т or '')))
    return ц[-10:] if len(ц) >= 10 else ''


def main():
    # ---- что видит сайт
    with centro_catalog.connect() as conn:
        табл = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print('таблицы базы панели:', ', '.join(табл))
        люди_панель = set()
        тел_панель = set()
        for имя in ('person', 'persons', 'people', 'contact', 'contacts'):
            if имя not in табл:
                continue
            кол = {r[1] for r in conn.execute(
                f'PRAGMA table_info({имя})').fetchall()}
            ряды = conn.execute(f'SELECT * FROM {имя}').fetchall()
            имена_кол = [c for c in ('person', 'fio', 'imya', 'name')
                         if c in кол]
            тел_кол = [c for c in ('phone', 'telefon', 'value') if c in кол]
            инн_кол = 'inn' if 'inn' in кол else None
            for r in ряды:
                d = dict(zip([c[1] for c in conn.execute(
                    f'PRAGMA table_info({имя})').fetchall()], r)) if not isinstance(r, dict) else r
                инн = str(d.get(инн_кол) or '').strip() if инн_кол else ''
                for c in имена_кол:
                    if d.get(c):
                        люди_панель.add((инн, клч(d[c])))
                for c in тел_кол:
                    ц = д10(d.get(c))
                    if ц:
                        тел_панель.add((инн, ц))
            print(f'  {имя}: строк {len(ряды)}')
    print(f'ЛЮДЕЙ на сайте: {len(люди_панель)}, телефонов: {len(тел_панель)}')

    # ---- что есть у меня
    db = EDB.EnrichDB()
    q = db.cx.execute
    люди_мои = {(и, клч(ф)) for и, ф in
                q('SELECT inn, person FROM people').fetchall() if ф}
    тел_мои = set()
    for и, т in q('SELECT inn, phone FROM phone_contacts').fetchall():
        ц = д10(т)
        if ц:
            тел_мои.add((и, ц))
    for и, т in q("SELECT inn, COALESCE(phone,'') FROM people").fetchall():
        ц = д10(т)
        if ц:
            тел_мои.add((и, ц))
    print(f'ЛЮДЕЙ у меня в enrich.db: {len(люди_мои)}, телефонов: {len(тел_мои)}')

    # ---- и в общей базе на дропе
    путь = os.path.join(ДРОП, 'BAZA-CENTROBEZHNIKI-OBSHCHAYA.csv')
    люди_свод = set()
    if os.path.exists(путь):
        csv.field_size_limit(10 ** 7)
        for r in csv.DictReader(io.StringIO(
                open(путь, encoding='utf-8-sig', errors='replace').read()),
                delimiter=';'):
            if (r.get('fio') or '').strip():
                люди_свод.add(((r.get('inn') or '').strip(), клч(r['fio'])))
        print(f'ЛЮДЕЙ в общей базе на дропе: {len(люди_свод)}')

    # ---- главное: чего сайт НЕ показывает
    инн_панели = {и for и, _ in люди_панель} | {и for и, _ in тел_панель}
    нет_на_сайте = {x for x in люди_свод if x[0] in инн_панели} - люди_панель
    print()
    print('=== ЧЕГО ПРОДАВЕЦ НЕ ВИДИТ ===')
    print(f'  людей есть у нас, нет на сайте (по тем же предприятиям): '
          f'{len(нет_на_сайте)}')
    тел_нет = {x for x in тел_мои if x[0] in инн_панели} - тел_панель
    print(f'  телефонов есть у нас, нет на сайте: {len(тел_нет)}')
    прим = Counter(и for и, _ in нет_на_сайте)
    if прим:
        print('  предприятия с самым большим отрывом:')
        for и, n in прим.most_common(8):
            print(f'    {и}: не показано {n} человек')


if __name__ == '__main__':
    main()
