# -*- coding: utf-8 -*-
"""Полная карточка по 382 предприятиям «имеют» + «покупали ранее».

Владелец просит один файл, где по этим предприятиям собрано ВСЁ, что у нас
есть: выручка из базы обзвона, ОКВЭД, реквизиты, люди, телефоны, состояние.

Почему это не берётся из присланных файлов напрямую: в их разделе СВОДКА
реквизиты редкие — выручка заполнена у 17 из 198, ОКВЭД у 34, регион у 31.
Полные реквизиты лежат в `companies` моей enrich.db и в базе обзвона
(161 761 юрлицо), и джойнить надо оттуда, иначе выгрузка будет выглядеть
заполненной, а по факту пустой.

Один ряд — одно предприятие. Люди сворачиваются в колонки-списки, чтобы
продавец видел карточку целиком, а не искал строки по файлу.

Запуск: python svod_382.py
"""
import csv
import io
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402
import enrich_contacts as EC  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'
ПАПКА = r'C:\sender\server'
ИМЯ = 'SVOD-382-imeyut-i-pokupali-POLNYY.csv'
ИСТОЧНИКИ = [('IMEYUT-198-vozdushnye-centrobezhnye.csv', 'имеют'),
             ('POKUPALI-RANEE-184-vozdushnye-centrobezhnye.csv', 'покупали ранее')]


def читать(имя):
    п = os.path.join(ДРОП, имя)
    if not os.path.exists(п):
        print(f'  НЕТ файла {имя}')
        return []
    csv.field_size_limit(10 ** 7)
    return list(csv.DictReader(
        io.StringIO(open(п, encoding='utf-8-sig', errors='replace').read()),
        delimiter=';'))


def на_дроп(путь, имя):
    import urllib.request
    урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
    зпр = urllib.request.Request(
        урл.rstrip('/') + '/' + имя, data=open(путь, 'rb').read(), method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    with urllib.request.urlopen(зпр, timeout=300) as о:
        return о.read()[:200]


def main():
    db = EDB.EnrichDB()
    q = db.cx.execute
    тех = set(EDB.EnrichDB.TECH_ROLES)

    # ---------- 1. предприятия из присланных файлов
    предпр = {}
    люди_вх = defaultdict(list)
    for файл, пометка in ИСТОЧНИКИ:
        ряды = читать(файл)
        for r in ряды:
            инн = (r.get('inn') or '').strip()
            if not инн:
                continue
            раздел = r.get('razdel') or ''
            з = предпр.setdefault(инн, {'пометки': set(), 'свод': {}})
            з['пометки'].add(пометка)
            if раздел == 'СВОДКА':
                з['свод'] = r
            elif раздел.startswith('ЧЕЛОВЕК'):
                люди_вх[инн].append((
                    (r.get('imya') or r.get('chelovek') or '').strip(),
                    (r.get('dolzhnost') or '').strip(),
                    (r.get('telefon') or r.get('telefon_cheloveka') or '').strip(),
                    раздел))
        print(f'{файл}: строк {len(ряды)}')
    print(f'предприятий всего: {len(предпр)}')

    # ---------- 2. реквизиты из companies (моя база)
    кол = {r[1] for r in q('PRAGMA table_info(companies)').fetchall()}
    выр = 'revenue_rub' if 'revenue_rub' in кол else 'pxr'
    комп = {}
    for r in q(f"SELECT inn, COALESCE(name,''), COALESCE(okved,''), "
               f"COALESCE(region,''), COALESCE({выр},''), COALESCE(site,''), "
               "COALESCE(best_email,''), COALESCE(phones,''), "
               "COALESCE(activity,'') FROM companies").fetchall():
        комп[r[0]] = r
    есть_комп = sum(1 for и in предпр if и in комп)
    print(f'нашлось в companies: {есть_комп} из {len(предпр)}')

    # ---------- 3. база обзвона: выручка и реквизиты по 161 761 юрлицу
    #
    # ДВЕ МОИ ОШИБКИ, найденные разведкой, обе давали «данных нет» вместо
    # «джойн не сошёлся»:
    #  1) ИНН с ведущим нулём. В выгрузке обзвона он местами потерян (Excel
    #     режет нули), поэтому сравнивать надо по нормализованному ключу, а не
    #     по строке. Первый прогон нашёл 48 предприятий из 375 — выглядело как
    #     «их нет в базе обзвона», а было расхождение формата.
    #  2) имена колонок. Я искал 'ОКВЭД'/'Выручка', а в файле
    #     'ОсновнойОКВЭД' и 'Выручка, руб.'. Поле оставалось пустым молча.
    def _кинн(x):
        ц = re.sub(r'\D', '', str(x or ''))
        return ц.lstrip('0') or ц

    хочу = {_кинн(и): и for и in предпр}
    обз = {}
    import glob as _g
    кандидаты = sorted(_g.glob(os.path.join(ДРОП, 'obzvon_all*.csv')))
    for п in кандидаты:
        csv.field_size_limit(10 ** 7)
        with open(п, encoding='utf-8-sig', errors='replace', newline='') as f:
            for r in csv.DictReader(f, delimiter=';'):
                к = _кинн(r.get('ИНН') or r.get('inn'))
                если = хочу.get(к)
                if если and если not in обз:
                    обз[если] = r
        print(f'база обзвона {os.path.basename(п)}: нашлось {len(обз)} '
              f'из {len(предпр)}')
        break
    else:
        print('  базы обзвона не нашёл — выручка только из companies')

    # ---------- 4. люди из моей базы
    люди_бд = defaultdict(list)
    for инн, фио, пост, роль, тел, поч, ист, урл in q(
            "SELECT inn, person, COALESCE(post,''), COALESCE(role,''), "
            "COALESCE(phone,''), COALESCE(email,''), COALESCE(source,''), "
            "COALESCE(source_url,'') FROM people").fetchall():
        if инн in предпр:
            люди_бд[инн].append((фио, пост, роль, тел, поч, ист, урл))

    # телефоны предприятия
    тел_бд = defaultdict(set)
    for инн, тел in q('SELECT inn, phone FROM phone_contacts').fetchall():
        if инн in предпр and (тел or '').strip():
            тел_бд[инн].add(тел.strip())

    # ---------- 5. сборка, один ряд — одно предприятие
    строки = []
    for инн in sorted(предпр):
        з = предпр[инн]
        с = з['свод']
        к = комп.get(инн)
        o = обз.get(инн, {})

        def обз_поле(*имена):
            for н in имена:
                v = (o.get(н) or '').strip()
                if v:
                    return v
            return ''

        выручка = (обз_поле('Выручка, руб.', 'Выручка')
                   or (str(к[4]) if к and к[4] else '')
                   or (с.get('vyruchka_rub') or ''))
        оквэд = (обз_поле('ОсновнойОКВЭД') or (с.get('okved') or '')
                 or (к[2] if к else ''))
        регион = (обз_поле('Регион') or (с.get('region') or '')
                  or (к[3] if к else ''))
        сайт = ((с.get('sayt') or с.get('sajt') or '') or (к[5] if к else '')
                or обз_поле('Сайты', 'Сайт'))
        почта = ((с.get('luchshaya_pochta') or '') or (к[6] if к else '')
                 or обз_поле('Emails', 'Email с сайта'))
        директор = (с.get('direktor') or '') or обз_поле('Директор')
        статус = (с.get('status_egrul') or '') or обз_поле('Статус')
        адрес = (с.get('adres') or '') or обз_поле('Адрес')
        ссч = обз_поле('ССЧ')
        прибыль = обз_поле('ЧистПрибыль')
        балл = обз_поле('Итоговый балл приоритета')
        оборуд = обз_поле('Все категории оборудования',
                          'Оборудование по основному ОКВЭД')
        тел_обз = обз_поле('Телефоны', 'Телефоны с сайта')

        нб = люди_бд.get(инн, [])
        нвх = люди_вх.get(инн, [])
        техн = [x for x in нб if x[2] in тех or x[2] == 'техконтакт']
        все_тел = sorted(тел_бд.get(инн, set()) |
                         {t for _, _, t, _ in нвх if t})
        строки.append([
            инн, (с.get('predpriyatie') or (к[1] if к else '')),
            ' | '.join(sorted(з['пометки'])),
            с.get('tipy_mashin', '')[:80], с.get('sreda_dokazana', ''),
            с.get('marki', '')[:120], с.get('sostoyaniy', ''),
            с.get('vyvod_ekspertizy', '')[:60], с.get('data_zakluchenia', ''),
            выручка, прибыль, ссч, балл, оквэд, оборуд[:80], регион,
            адрес[:90], статус, директор,
            сайт, почта,
            ' | '.join(все_тел[:6]),
            (тел_обз or с.get('telefony_predpriyatiya') or '')[:70],
            len(нб), len(техн), len(нвх),
            ' | '.join(f'{f} ({p or роль})' for f, p, роль, *_ in техн[:6]),
            ' | '.join(f'{f} ({p}) {t}'.strip() for f, p, t, _ in нвх[:6]),
            с.get('proverok_nadzora_2025_2026', ''),
            с.get('v_baze_obzvona', '') or ('да' if o else 'нет'),
            с.get('segment', ''), с.get('novost', '')[:80],
            с.get('novost_ssylka', ''), с.get('chego_ne_hvataet', '')[:80]])

    путь = os.path.join(ПАПКА, ИМЯ)
    with open(путь, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow([
            'inn', 'predpriyatie', 'pometka', 'tipy_mashin', 'sreda',
            'marki', 'sostoyaniy', 'vyvod_ekspertizy', 'data_zakluchenia',
            'vyruchka_rub', 'chistaya_pribyl', 'ssch', 'ball_prioriteta',
            'okved', 'oborudovanie_po_okved', 'region', 'adres', 'status_egrul',
            'direktor', 'sayt', 'pochta', 'telefony_iz_bazy',
            'telefony_predpriyatiya', 'lyudej_v_baze', 'tehnicheskih',
            'lyudej_iz_faylov', 'tehnicheskie_lyudi', 'lyudi_iz_faylov',
            'proverok_nadzora', 'v_baze_obzvona', 'segment', 'novost',
            'novost_ssylka', 'chego_ne_hvataet'])
        в.writerows(строки)
        ф.flush()
        os.fsync(ф.fileno())

    # числа перечитыванием
    n = свыр = сокв = стех = стел = 0
    with open(путь, encoding='utf-8-sig', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            n += 1
            if r['vyruchka_rub'].strip():
                свыр += 1
            if r['okved'].strip():
                сокв += 1
            if r['tehnicheskie_lyudi'].strip():
                стех += 1
            if r['telefony_iz_bazy'].strip() or r['telefony_predpriyatiya'].strip():
                стел += 1
    print()
    print('=== ЧИСЛА ПЕРЕЧИТЫВАНИЕМ ФАЙЛА ===')
    print(f'  предприятий: {n}')
    print(f'  с выручкой: {свыр}   с ОКВЭД: {сокв}')
    print(f'  с техническими людьми: {стех}   с телефоном: {стел}')
    try:
        на_дроп(путь, ИМЯ)
        print(f'  на дропе: {ИМЯ}')
    except Exception as e:  # noqa: BLE001
        print(f'  на дроп НЕ легло: {str(e)[:120]}')


if __name__ == '__main__':
    main()
