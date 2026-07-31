# -*- coding: utf-8 -*-
"""ОБЩАЯ БАЗА ПО ЦЕНТРОБЕЖНИКАМ — свод трёх сессий в один файл для продажников.

Владелец: у всех троих 4% недельного лимита, надо добить хотя бы это. Поэтому
скрипт берёт ТОЛЬКО то, что уже лежит на дропе, и ни у кого ничего не просит.

Что складывается:
  1. `OCHERED-centrobezhnye.csv` — 1853 предприятия, тип доказан реестром ЭПБ
     (вторая сессия). Проверено: чистый токен «центробежная» есть у всех 1853,
     ни одно не держится на одной лишь помеченной примеси.
  2. Люди из колонки `lyudi_podrobno` той же очереди.
  3. `SVOD-LICHNYE-NOMERA.csv` — уже сведённые личные номера первой и третьей.
  4. `CEL-centrobezhnye-tehniki-s-nomerom.csv` — технари третьей сессии.
  5. `people` из моей `enrich.db` — с ролью, датой факта и ссылкой.

Три правила, выведенные сегодня на своих же ошибках, соблюдены здесь буквально.

**Разбор `lyudi_podrobno` не доверяет позиции поля.** Строка выглядит как
`ФИО | должность | телефон | телефон | источник`, но у части записей должность
занимает две ячейки, у части её нет вовсе, а хвост обрезан по длине. Брать
телефон «третьим полем» значит рано или поздно приписать человеку чужой номер.
Поэтому ФИО берётся первым полем, должность вторым, а ТЕЛЕФОНЫ вылавливаются
регуляркой по всему отрезку между `;;` — граница отрезка и есть граница
человека, и она надёжна, а порядок полей внутри — нет.

**Проигравшее при склейке сохраняется** (`varianty_*`, `rasxozhdeniya`).
Склейка отбрасывает тихо, и снаружи это неотличимо от согласия источников.

**Предприятие без единого человека остаётся в файле** со своей строкой и
пометкой, чего не хватает. Выбросить его — значит показать продавцу базу, в
которой «везде есть люди», и спрятать настоящий объём работы.

Запуск: python baza_centrobezhniki.py
"""
import csv
import io
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'
ПАПКА = r'C:\sender\server'
ИМЯ = 'BAZA-CENTROBEZHNIKI-OBSHCHAYA.csv'

_ДОБ = re.compile(r'\s*(?:доб|вн|внутр|ext)\.?\s*[:№]?\s*[\d\-]+\s*$', re.I)
_ТЕЛ = re.compile(r'(?:\+?7|8)?[\s(\-]*\d{3,5}[\s)\-]*\d[\d\s\-]{5,10}\d')
_МОБ = re.compile(r'(?:\+?7|8)\D{0,3}9\d\d')
_800 = re.compile(r'8\D{0,3}800')


def клч(т):
    return re.sub(r'\s+', ' ', str(т or '').strip().lower()).replace('ё', 'е')


def д10(т):
    ц = re.sub(r'\D', '', _ДОБ.sub('', str(т or '')))
    return ц[-10:] if len(ц) >= 10 else ''


def похоже_на_фио(т):
    """Полное имя: два слова и больше."""
    т = (т or '').strip()
    if not (6 <= len(т) <= 60):
        return False
    сл = т.split()
    return len(сл) >= 2 and all(s[:1].isalpha() for s in сл[:2])


def только_имя(т):
    """ОДНО слово — неполная, но живая запись.

    Поймано сверкой со сводом: предприятие 1006004155 пропало из базы, хотя в
    своде у него есть «Алексей, гл.механик, +7 911 415-12-22». Мой фильтр
    требовал двух слов и выбросил запись МОЛЧА — ровно то, против чего я сам
    сегодня возражал третьей сессии: отбрасывать надо с причиной и не терять.

    Для продавца «Алексей, главный механик» с личным мобильным — рабочий
    контакт, а не мусор. Поэтому такие записи принимаются, но помечаются:
    неполное имя видно в колонке расхождений.
    """
    т = (т or '').strip()
    сл = т.split()
    return len(сл) == 1 and 3 <= len(т) <= 30 and т[:1].isalpha()


def читать(имя):
    п = os.path.join(ДРОП, имя)
    if not os.path.exists(п):
        print(f'  НЕТ файла {имя} — пропускаю, но это дыра, а не норма')
        return []
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

    # ---------- 0. подтверждённое состояние по факту (SVODNAYA-centrobezhnye.csv,
    # третья сессия). `est`/`pokupaet`/`planiruet` в OCHERED — сумма ВСЕГО реестра
    # ЭПБ предприятия (там вперемешку движки КАМАЗ и газопроводы), это НЕ
    # подтверждённые числа, владелец указал считать по факту с фильтром
    # tip_mashiny центробежная + sreda воздух. Один факт — одна пометка.
    def _чист_тип(t):
        return any(x.strip().startswith('центробежн') and 'насос' not in x
                   for x in (t or '').split('|'))
    состояние = defaultdict(lambda: {'пометки': set(), 'ссылка': '', 'дата': ''})
    for r in читать('SVODNAYA-centrobezhnye.csv'):
        if _чист_тип(r.get('tip_mashiny')) and r.get('sreda') == 'воздух':
            з = состояние[(r.get('inn') or '').strip()]
            п = (r.get('pometka') or '').strip()
            if п:
                з['пометки'].add(п)
            if not з['ссылка'] and (r.get('ssylka_na_istochnik') or '').strip():
                з['ссылка'] = r['ssylka_na_istochnik'].strip()
            if not з['дата'] and (r.get('data_dokazatelstva') or '').strip():
                з['дата'] = r['data_dokazatelstva'].strip()
    print(f'предприятий с подтверждённым фактом (центробежная+воздух): '
          f'{len(состояние)}')
    for п in ('покупают', 'уже есть', 'планируют покупать', 'покупали ранее'):
        print(f'  {sum(1 for з in состояние.values() if п in з["пометки"])}  {п}')

    # ---------- 1. предприятия
    очередь = читать('OCHERED-centrobezhnye.csv')
    предпр = {}
    for r in очередь:
        инн = (r.get('inn') or '').strip()
        if инн:
            предпр[инн] = r
    print(f'предприятий в очереди центробежных: {len(предпр)}')

    # ---------- 2. люди
    люди = defaultdict(list)      # (инн, клч(фио)) -> список наблюдений

    def добавить(инн, фио, долж, телефоны, роль_авт, чьё, ист, урл, дата,
                 что_дата, роль_готовая='', техл_готовый=''):
        фио = (фио or '').strip()
        if инн not in предпр:
            return
        полное = похоже_на_фио(фио)
        if not полное and not (только_имя(фио) and any(телефоны)):
            return
        люди[(инн, клч(фио))].append({
            'фио': фио, 'долж': (долж or '').strip(),
            'имя_неполное': not полное,
            'тел': [t for t in телефоны if t], 'роль_авт': (роль_авт or '').strip(),
            # Роль, УЖЕ посчитанная общим каноном в своде. Пересчитывать её
            # здесь заново значит держать вторую копию логики: у меня она
            # сразу и разошлась — свод дал 21 предприятие с техническим
            # мобильным, база 20. Один и тот же факт, посчитанный дважды,
            # расходится всегда; вопрос только когда это заметят.
            'роль_готовая': (роль_готовая or '').strip(),
            'техл_готовый': (техл_готовый or '').strip(),
            'чьё': чьё, 'ист': (ист or '').strip(), 'урл': (урл or '').strip(),
            'дата': (дата or '').strip(), 'что_дата': (что_дата or '').strip()})

    # 2а. lyudi_podrobno очереди
    из_очереди = 0
    for инн, r in предпр.items():
        блок = (r.get('lyudi_podrobno') or '').strip()
        if not блок:
            continue
        for кусок in блок.split(';;'):
            поля = [p.strip() for p in кусок.split('|')]
            if not поля or not похоже_на_фио(поля[0]):
                continue
            # телефоны — регуляркой по ВСЕМУ отрезку, не по номеру поля
            телы = [д10(m.group(0)) for m in _ТЕЛ.finditer(кусок)]
            долж = поля[1] if len(поля) > 1 and not _ТЕЛ.search(поля[1]) else ''
            добавить(инн, поля[0], долж, телы, '', '2-я сессия',
                     'Tender.pro (очередь ЭПБ)', '', '', '')
            из_очереди += 1
    print(f'людей из lyudi_podrobno очереди: {из_очереди}')

    # 2б. сведённые личные номера (первая + третья)
    из_свода = 0
    for r in читать('SVOD-LICHNYE-NOMERA.csv'):
        инн = (r.get('inn') or '').strip()
        добавить(инн, r.get('fio'), r.get('dolzhnost'),
                 [д10(r.get('nomer_10cifr'))], r.get('rol_avtora'),
                 'свод 1+3', r.get('istochnik'), '',
                 r.get('data_sobytiya'), r.get('chto_za_data'),
                 роль_готовая=r.get('rol_kanon'), техл_готовый=r.get('tehLPR'))
        из_свода += 1 if инн in предпр else 0
    print(f'людей из свода личных номеров (попавших в очередь): {из_свода}')

    # 2в1. люди с сайтов (водоканальский обход --lica). Естественно
    # отфильтруются добавить()-ом по членству ИНН в очереди — те 35 из 49
    # предприятий, что в очередь не входят (чистые водоканалы), сюда не
    # попадут, это верно: у базы центробежников свой список предприятий.
    из_сайтов = 0
    for r in читать('lica-s-sajtov.csv'):
        инн = (r.get('inn') or '').strip()
        добавить(инн, r.get('imya'), r.get('dolzhnost'),
                 [д10(r.get('telefon'))], r.get('rol'), 'обход сайтов',
                 (r.get('chto_za_stranica') or 'страница сайта')[:60],
                 r.get('sajt') or '', '', '')
        из_сайтов += 1 if инн in предпр else 0
    print(f'людей с сайтов lica-s-sajtov (попавших в очередь): {из_сайтов}')

    # 2в2. вложения закупок ЕИС (третья сессия), ИНН резолвится по карте
    # zakupka->inn, которую она же оставила. Без карты zakupka в файле нет
    # ИНН вовсе — это её колонки, «zakupka» не «inn», сама база решить не
    # может, к какому предприятию относится строка.
    # Полная карта на все 50 закупок (третья сессия). Прежний файл
    # eis-tehniki-bez-nomera-dlya-1-sessii.csv покрывал 16 из 50, и 27
    # технических людей из 59 молча не доезжали до базы — «нет ИНН» выглядело
    # как свойство вложений, а было нехваткой карты.
    zk_inn = {r['zakupka']: (r.get('inn') or '').strip()
              for r in читать('eis-zakupka-inn-karta.csv')}
    for r in читать('eis-tehniki-bez-nomera-dlya-1-sessii.csv'):
        zk_inn.setdefault(r['zakupka'], (r.get('inn') or '').strip())
    вложения = читать('vlozheniya-lica.csv')
    из_вложений = с_инн = 0
    for r in вложения:
        инн = zk_inn.get((r.get('zakupka') or '').strip(), '')
        if not инн:
            continue
        с_инн += 1
        добавить(инн, r.get('imya'), r.get('dolzhnost'),
                 [д10(r.get('telefon'))], r.get('rol'), '3-я сессия (вложения)',
                 'вложение ЕИС, закупка ' + (r.get('zakupka') or ''), '', '', '')
        из_вложений += 1 if инн in предпр else 0
    print(f'людей из вложений ЕИС: строк {len(вложения)}, с известным ИНН '
          f'{с_инн}, попавших в очередь {из_вложений}')

    # 2в. технари третьей сессии
    из_цел = 0
    for r in читать('CEL-centrobezhnye-tehniki-s-nomerom.csv'):
        инн = (r.get('inn') or r.get('ИНН') or '').strip()
        добавить(инн, r.get('fio') or r.get('imya') or r.get('ФИО'),
                 r.get('dolzhnost') or r.get('должность'),
                 [д10(r.get('telefon') or r.get('nomer_10cifr') or '')],
                 r.get('rol') or 'техническая', '3-я сессия',
                 r.get('istochnik') or 'Тендер.Про', r.get('ssylka') or '',
                 r.get('data_fakta') or '', '')
        из_цел += 1 if инн in предпр else 0
    print(f'людей из CEL третьей сессии (попавших в очередь): {из_цел}')

    # 2г. мои люди из базы — с датой и ссылкой
    даты_мои = {}
    for r in читать('LYUDI-1-SESSIYA-s-datami.csv'):
        к = ((r.get('inn') or '').strip(), клч(r.get('fio')))
        if к[0]:
            даты_мои[к] = ((r.get('data_sobytiya') or '').strip(),
                           (r.get('chto_za_data') or '').strip())
    из_базы = 0
    for инн, фио, пост, роль, тел, поч, ист, урл in q(
            "SELECT inn, person, COALESCE(post,''), COALESCE(role,''), "
            "COALESCE(phone,''), COALESCE(email,''), COALESCE(source,''), "
            "COALESCE(source_url,'') FROM people").fetchall():
        if инн not in предпр:
            continue
        д, чд = даты_мои.get((инн, клч(фио)), ('', ''))
        добавить(инн, фио, пост, [д10(тел)], роль, '1-я сессия', ист, урл, д, чд)
        из_базы += 1
    print(f'моих людей из enrich.db (попавших в очередь): {из_базы}')

    # ---------- 3. склейка человека, с сохранением проигравшего
    строки = []
    инн_с_людьми = set()
    for (инн, _к), набл in sorted(люди.items()):
        п = предпр[инн]
        набл.sort(key=lambda н: (bool(н['урл']), len(н['долж']), len(н['тел'])),
                  reverse=True)
        фио = набл[0]['фио']
        долж = next((н['долж'] for н in набл if н['долж']), '')
        # порядок: готовая роль из свода → канон по должности → роль автора
        гот = next((н for н in набл if н['роль_готовая']), None)
        if гот:
            роль, осн = гот['роль_готовая'], 'общий канон свода'
        else:
            роль = EDB.EnrichDB._canon_role(долж) or ''
            осн = 'должность' if роль else 'нет'
            if not роль:
                ра = next((н['роль_авт'] for н in набл if н['роль_авт']), '')
                if ра and (ра in тех or ра in ('техконтакт', 'снабжение/закупки')
                           or клч(ра).startswith('техни')):
                    роль = ра if ра in тех or ра == 'снабжение/закупки' else 'техконтакт'
                    осн = 'роль автора'
        техл = роль in тех or роль == 'техконтакт'
        if гот and гот['техл_готовый'] == 'да':
            техл = True

        все_тел = list(dict.fromkeys([t for н in набл for t in н['тел'] if t]))
        моб = [t for t in все_тел if t.startswith('9')]
        дата = next((н['дата'] for н in набл if н['дата']), '')
        чд = next((н['что_дата'] for н in набл if н['что_дата']), '')
        if дата and not чд:
            чд = 'дата факта, как её дал источник'
        if not дата:
            чд = 'даты нет: источник её не публикует'
        урл = next((н['урл'] for н in набл if н['урл']), '')
        ист = '; '.join(dict.fromkeys(н['ист'] for н in набл if н['ист']))[:120]
        # Имена сессий приводим к одному написанию: в своде они лежат как
        # `1-SESSIYA`, у меня как `1-я сессия`, и в отчёте это выглядит как
        # разные источники, хотя источник один.
        _ИМЯ = {'1-SESSIYA': '1-я сессия', '2-SESSIYA': '2-я сессия',
                '3-SESSIYA': '3-я сессия', 'свод 1+3': '1-я сессия,3-я сессия'}
        нб = set()
        for н in набл:
            for ч in str(н['чьё']).split(','):
                ч = ч.strip()
                нб.update(x.strip() for x in _ИМЯ.get(ч, ч).split(','))
        чьи = ','.join(sorted(x for x in нб if x))

        видно = {клч(долж)}
        вард = []
        for н in набл:
            if н['долж'] and клч(н['долж']) not in видно:
                видно.add(клч(н['долж']))
                вард.append(н['долж'])
        видно_и = {клч(фио)}
        вари = []
        for н in набл:
            if клч(н['фио']) not in видно_и:
                видно_и.add(клч(н['фио']))
                вари.append(н['фио'])
        расх = ([('должность' if вард else '')] + [('имя' if вари else '')]
                + [('несколько номеров' if len(все_тел) > 1 else '')]
                + [('ИМЯ НЕПОЛНОЕ: без фамилии'
                    if all(н['имя_неполное'] for н in набл) else '')])
        инн_с_людьми.add(инн)
        з = состояние.get(инн, {'пометки': set(), 'ссылка': '', 'дата': ''})
        строки.append([
            инн, (п.get('predpriyatie') or '')[:70], (п.get('region') or '')[:30],
            (п.get('tipy_mashin') or '')[:60], (п.get('sreda_dokazana') or ''),
            (п.get('sayt') or '')[:60],
            фио, долж[:90], роль, осн, 'да' if техл else 'нет',
            моб[0] if моб else '', ' | '.join(все_тел[:4]),
            'мобильный' if моб else ('городской' if все_тел else 'номера нет'),
            (п.get('luchshaya_pochta') or '')[:60],
            дата, чд, чьи, ист, урл,
            ' | '.join(вард)[:200], ' | '.join(вари)[:150],
            ' + '.join([x for x in расх if x]),
            ' | '.join(sorted(з['пометки'])), з['ссылка'], з['дата']])

    # ---------- 4. предприятия БЕЗ единого человека — остаются в файле
    без_людей = 0
    for инн, п in sorted(предпр.items()):
        if инн in инн_с_людьми:
            continue
        без_людей += 1
        з = состояние.get(инн, {'пометки': set(), 'ссылка': '', 'дата': ''})
        строки.append([
            инн, (п.get('predpriyatie') or '')[:70], (п.get('region') or '')[:30],
            (п.get('tipy_mashin') or '')[:60], (п.get('sreda_dokazana') or ''),
            (п.get('sayt') or '')[:60],
            '', '', '', 'нет', 'нет', '',
            (п.get('telefony_predpriyatiya') or '')[:60],
            'только общий номер' if (п.get('telefony_predpriyatiya') or '').strip()
            else 'номера нет',
            (п.get('luchshaya_pochta') or '')[:60], '',
            'даты нет: человека не нашли', '', '', '', '', '',
            'ЧЕЛОВЕК НЕ НАЙДЕН',
            ' | '.join(sorted(з['пометки'])), з['ссылка'], з['дата']])

    путь = os.path.join(ПАПКА, ИМЯ)
    with open(путь, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow([
            'inn', 'predpriyatie', 'region', 'tip_mashiny', 'sreda', 'sayt',
            'fio', 'dolzhnost', 'rol_kanon', 'osnovanie_roli', 'tehLPR',
            'mobilnyy_10cifr', 'vse_nomera', 'vid_nomera', 'pochta',
            'data_fakta', 'chto_za_data', 'ch_i_sessii', 'istochnik',
            'ssylka_na_istochnik', 'varianty_dolzhnosti', 'varianty_imeni',
            'rasxozhdeniya', 'sostoyanie_potverzhdeno_faktom',
            'ssylka_sostoyaniya', 'data_dokazatelstva_sostoyaniya'])
        в.writerows(строки)
        ф.flush()
        os.fsync(ф.fileno())

    # ---------- 5. числа ПЕРЕЧИТЫВАНИЕМ файла
    вс = слюдьми = техл = смоб = техмоб = 0
    инн_все, инн_тех, инн_техмоб = set(), set(), set()
    чьи = Counter()
    with open(путь, encoding='utf-8-sig', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            вс += 1
            инн_все.add(r['inn'])
            if not r['fio']:
                continue
            слюдьми += 1
            чьи[r['ch_i_sessii']] += 1
            if r['tehLPR'] == 'да':
                техл += 1
                инн_тех.add(r['inn'])
            if r['mobilnyy_10cifr']:
                смоб += 1
                if r['tehLPR'] == 'да':
                    техмоб += 1
                    инн_техмоб.add(r['inn'])
    print()
    print('=== ОБЩАЯ БАЗА, ЧИСЛА ПЕРЕЧИТЫВАНИЕМ ФАЙЛА ===')
    print(f'  строк всего: {вс}, предприятий: {len(инн_все)}')
    print(f'  строк с человеком: {слюдьми}')
    print(f'  предприятий БЕЗ единого человека: {без_людей} '
          f'({round(100 * без_людей / max(1, len(инн_все)))}%)')
    print(f'  ТЕХНИЧЕСКИХ людей: {техл} на {len(инн_тех)} предприятиях')
    print(f'  людей с мобильным: {смоб}')
    print(f'  ТЕХНИЧЕСКИЙ + ЛИЧНЫЙ МОБИЛЬНЫЙ: {техмоб} '
          f'на {len(инн_техмоб)} предприятиях')
    print('  чьи люди:')
    for к, n in чьи.most_common(8):
        print(f'    {n:>5}  {к}')
    try:
        на_дроп(путь, ИМЯ)
        print(f'  на дропе: {ИМЯ}')
    except Exception as e:  # noqa: BLE001
        print(f'  на дроп НЕ легло: {str(e)[:120]}')
    print(f'строк {вс}, предприятий {len(инн_все)}, техЛПР {техл}, '
          f'с мобильным {техмоб}')


if __name__ == '__main__':
    main()
