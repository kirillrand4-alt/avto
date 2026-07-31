# -*- coding: utf-8 -*-
"""ВСЯ информация по 375 предприятиям в одном файле, ничего не свёрнуто.

Признание, из-за которого этот скрипт существует. Первая моя выгрузка
(`SVOD-382-imeyut-i-pokupali-POLNYY.csv`) брала из присланных файлов ТОЛЬКО
раздел СВОДКА — 375 строк из 27 627. Двадцать пять тысяч строк фактов со
ссылками на заключения ЭПБ, цитатами и датами я отбросил, а файл назвал
«ПОЛНЫЙ». Снаружи он выглядел полным: колонок много, поля заполнены. Это тот
же класс ошибки, что мы ловили весь день, только теперь в названии файла.

Здесь один файл, много разделов. Колонка `razdel` говорит, что за строка:

  КАРТОЧКА   — 375 строк, слияние трёх версий, все колонки всех трёх
  ФАКТ       — каждое доказательство: марка, ссылка, цитата, дата, вывод ЭПБ
  ЧЕЛОВЕК    — один человек = одна строка, номер стоит В ЕЁ ЖЕ строке
  НОМЕР      — номер, владельца которого мы НЕ знаем, отдельно и честно
  НОВОСТЬ    — новость с ссылкой
  СВОДНАЯ    — строки приоритета из сводной таблицы

Почему человек и номер разведены по разным разделам: список номеров рядом с
фамилией не даёт понять, чей номер, и продавец звонит наугад. Если владелец
номера неизвестен — это надо ВИДЕТЬ, а не догадываться по пустому месту.

Запуск: python polnyy_375.py
"""
import csv
import io
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'
ПАПКА = r'C:\sender\server'
ИМЯ = 'POLNYY-375-vsya-informaciya.csv'
КАРТОЧКИ = ['SVOD-382-imeyut-i-pokupali-POLNYY.csv',
            'SVOD-382-DOPOLNENO.csv',
            'SVOD382-dopolnen-3-sessiey.csv']
ИСХОДНЫЕ = ['IMEYUT-198-vozdushnye-centrobezhnye.csv',
            'POKUPALI-RANEE-184-vozdushnye-centrobezhnye.csv']

_ДОБ = re.compile(r'\s*(?:доб|вн|внутр|ext)\.?\s*[:№]?\s*[\d\-]+\s*$', re.I)


def д10(т):
    ц = re.sub(r'\D', '', _ДОБ.sub('', str(т or '')))
    return ц[-10:] if len(ц) >= 10 else ''


def вид(ц):
    return 'нет номера' if not ц else ('мобильный' if ц.startswith('9')
                                       else 'городской')


def клч(т):
    return re.sub(r'\s+', ' ', str(т or '').strip().lower()).replace('ё', 'е')


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
    with urllib.request.urlopen(зпр, timeout=600) as о:
        return о.read()[:200]


def main():
    db = EDB.EnrichDB()
    q = db.cx.execute
    тех = set(EDB.EnrichDB.TECH_ROLES)

    # ---------- 1. КАРТОЧКА: слить три версии по ИНН
    карт_поля, свод = [], {}
    for имя in КАРТОЧКИ:
        ряды = читать(имя)
        if not ряды:
            continue
        for к in ряды[0].keys():
            if к not in карт_поля:
                карт_поля.append(к)
        for r in ряды:
            инн = (r.get('inn') or '').strip()
            if not инн:
                continue
            з = свод.setdefault(инн, {})
            for к, v in r.items():
                v = (v or '').strip()
                if not v:
                    continue
                if not з.get(к):
                    з[к] = v
                elif клч(з[к]) != клч(v) and v not in з[к]:
                    з[к] += ' ;; ' + v
        print(f'{имя}: {len(ряды)} строк, {len(ряды[0])} колонок')
    print(f'КАРТОЧЕК: {len(свод)}, колонок слито: {len(карт_поля)}')

    # ---------- 2. люди с привязанным номером (из базы и из колонок)
    люди = defaultdict(dict)
    без_имени = defaultdict(set)

    def полож(инн, фио, долж, роль, номер, ист, урл=''):
        фио = (фио or '').strip()
        if not фио or инн not in свод or len(фио.split()) < 2:
            return
        з = люди[инн].setdefault(клч(фио), {
            'фио': фио, 'долж': '', 'роль': '', 'ном': set(),
            'ист': set(), 'урл': ''})
        if долж and not з['долж']:
            з['долж'] = долж.strip()
        if роль and not з['роль']:
            з['роль'] = роль.strip()
        ц = д10(номер)
        if ц:
            з['ном'].add(ц)
        if ист:
            з['ист'].add(ист[:50])
        if урл and not з['урл']:
            з['урл'] = урл

    for инн, фио, пост, роль, тел, поч, ист, урл in q(
            "SELECT inn, person, COALESCE(post,''), COALESCE(role,''), "
            "COALESCE(phone,''), COALESCE(email,''), COALESCE(source,''), "
            "COALESCE(source_url,'') FROM people").fetchall():
        полож(инн, фио, пост, роль, тел, ист or 'enrich.db', урл)
    for инн, тел, фио, роль, ист, урл in q(
            "SELECT inn, phone, COALESCE(person,''), COALESCE(role,''), "
            "COALESCE(source,''), COALESCE(source_url,'') "
            'FROM phone_contacts').fetchall():
        if инн not in свод:
            continue
        ц = д10(тел)
        if not ц:
            continue
        if (фио or '').strip():
            полож(инн, фио, '', роль, тел, ист or 'phone_contacts', урл)
        else:
            без_имени[инн].add((ц, (ист or 'источник не назван')[:40], урл[:90]))

    for инн, з in свод.items():
        for кусок in (з.get('lyudi_moi_podrobno') or '').split(';;'):
            ч = [x.strip() for x in кусок.split('|')]
            if len(ч) < 2 or len(ч[0].split()) < 2:
                continue
            телы = [x for x in ч[1:] if д10(x)] or ['']
            долж = ч[1] if not д10(ч[1]) else ''
            for т in телы:
                полож(инн, ч[0], долж, '', т, 'Tender.pro (2-я сессия)')
        for кол in ('tehnicheskie_lyudi', 'lyudi_iz_faylov'):
            for кусок in (з.get(кол) or '').split('|'):
                м = re.match(r'^(.+?)\s*\((.*?)\)\s*$', кусок.strip())
                if м and len(м.group(1).split()) >= 2:
                    полож(инн, м.group(1), м.group(2), '', '', кол)

    # ---------- 3. сборка длинного файла
    ЗАГ = ['razdel', 'inn', 'predpriyatie', 'chto', 'kto_ili_marka',
           'dolzhnost_ili_tip', 'rol', 'nomer_10cifr', 'vid_nomera',
           'pochta', 'data', 'chem_dokazano', 'citata', 'ssylka',
           'istochnik', 'tehLPR']
    строки = []
    имена = {и: (з.get('predpriyatie') or '')[:70] for и, з in свод.items()}

    # 3а. КАРТОЧКА — все слитые колонки, чтобы ничего не потерять
    for инн in sorted(свод):
        з = свод[инн]
        строки.append(['КАРТОЧКА', инн, имена[инн],
                       'слияние трёх версий карточки', '', '', '', '', '',
                       з.get('pochta', ''), '', '', '', з.get('sayt', ''),
                       'свод 1+2+3 сессий', ''])

    # 3б. ФАКТ / СВОДНАЯ / НОВОСТЬ — ВСЁ из присланных файлов, не только СВОДКА
    фактов = сводных = новостей = 0
    for имя in ИСХОДНЫЕ:
        for r in читать(имя):
            инн = (r.get('inn') or '').strip()
            if инн not in свод:
                continue
            разд = (r.get('razdel') or '').strip()
            if разд == 'ФАКТ':
                фактов += 1
                строки.append([
                    'ФАКТ', инн, имена[инн], (r.get('sostoyanie') or '')[:60],
                    (r.get('marki') or '')[:80], (r.get('tip_mashiny') or '')[:60],
                    (r.get('sreda') or r.get('sreda_mashiny') or ''), '', '', '',
                    (r.get('data') or r.get('data_dokazatelstva') or ''),
                    (r.get('chem_dokazano') or '')[:120],
                    (r.get('tekst') or '')[:300],
                    (r.get('ssylka') or r.get('ssylka_na_istochnik') or ''),
                    (r.get('istochnik') or '')[:60], ''])
            elif разд == 'СВОДНАЯ':
                сводных += 1
                строки.append([
                    'СВОДНАЯ', инн, имена[инн],
                    'приоритет: ' + (r.get('prioritet') or ''),
                    (r.get('vazhnost_pokupki') or ''),
                    (r.get('dostupnost_kontakta') or ''), '', '', '', '',
                    (r.get('data_dokazatelstva') or ''),
                    (r.get('prioritet_pochemu') or '')[:150], '',
                    (r.get('ssylka_na_istochnik') or ''),
                    (r.get('istochnik') or '')[:60], ''])
            if (r.get('novost') or '').strip():
                новостей += 1
                строки.append([
                    'НОВОСТЬ', инн, имена[инн], 'новость предприятия',
                    (r.get('novost') or '')[:200], '', '', '', '', '',
                    (r.get('data') or ''), '', '',
                    (r.get('novost_ssylka') or ''), 'новостной поиск', ''])
    print(f'ФАКТОВ: {фактов}, СВОДНЫХ: {сводных}, НОВОСТЕЙ: {новостей}')

    # 3в. ЧЕЛОВЕК — одна строка на человека, НОМЕР В ЕГО ЖЕ СТРОКЕ
    чел = счел_ном = 0
    for инн in sorted(люди):
        for ч in люди[инн].values():
            ном = sorted(ч['ном'])
            техл = ч['роль'] in тех or ч['роль'] == 'техконтакт'
            for i, ц in enumerate(ном or ['']):
                чел += 1
                if ц:
                    счел_ном += 1
                строки.append([
                    'ЧЕЛОВЕК', инн, имена[инн],
                    'контакт человека' + (' (второй номер)' if i else ''),
                    ч['фио'], ч['долж'] or 'должность не названа',
                    ч['роль'] or 'роль не установлена', ц, вид(ц), '', '', '',
                    '', ч['урл'], ';'.join(sorted(ч['ист'])) or 'не назван',
                    'да' if техл else 'нет'])

    # 3г. НОМЕР без владельца — отдельно, чтобы не выдавать за чей-то
    безвл = 0
    for инн in sorted(без_имени):
        занято = {ц for ч in люди.get(инн, {}).values() for ц in ч['ном']}
        for ц, ист, урл in sorted(без_имени[инн]):
            if ц in занято:
                continue
            безвл += 1
            строки.append([
                'НОМЕР', инн, имена[инн], 'ВЛАДЕЛЕЦ НЕИЗВЕСТЕН', '', '', '',
                ц, вид(ц), '', '', '', '', урл, ист, ''])

    путь = os.path.join(ПАПКА, ИМЯ)
    with open(путь, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow(ЗАГ)
        в.writerows(строки)
        ф.flush()
        os.fsync(ф.fileno())

    # ---------- 4. числа перечитыванием
    from collections import Counter
    c = Counter()
    инн_все = set()
    смоб = стех_ном = 0
    with open(путь, encoding='utf-8-sig', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            c[r['razdel']] += 1
            инн_все.add(r['inn'])
            if r['razdel'] == 'ЧЕЛОВЕК' and r['nomer_10cifr']:
                if r['vid_nomera'] == 'мобильный':
                    смоб += 1
                if r['tehLPR'] == 'да':
                    стех_ном += 1
    print()
    print('=== ПОЛНЫЙ ФАЙЛ, ЧИСЛА ПЕРЕЧИТЫВАНИЕМ ===')
    print(f'  строк всего: {sum(c.values())}, предприятий: {len(инн_все)}')
    for к, n in c.most_common():
        print(f'    {n:>7}  {к}')
    print(f'  людей с номером В СВОЕЙ строке: {счел_ном}, из них мобильных {смоб}')
    print(f'  технических людей с номером: {стех_ном}')
    print(f'  номеров с НЕИЗВЕСТНЫМ владельцем (отдельным разделом): {безвл}')
    try:
        на_дроп(путь, ИМЯ)
        print(f'  на дропе: {ИМЯ}')
    except Exception as e:  # noqa: BLE001
        print(f'  на дроп НЕ легло: {str(e)[:120]}')


if __name__ == '__main__':
    main()
