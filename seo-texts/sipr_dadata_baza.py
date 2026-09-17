# -*- coding: utf-8 -*-
"""Добор ИНН по ЕГРЮЛ для заявителей ТП из СиПР + сверка с нашей базой. Идёт НА СЕРВЕРЕ.

ПОЧЕМУ НА СЕРВЕРЕ. Токен DaData лежит в окружении сервера, в песочнице его нет (проверено:
DADATA_TOKEN отсутствует, rs.env отсутствует). И живая база `PARK-BAZA-EDINAYA-3S.csv` тоже
лежит на сервере. Разбор PDF, наоборот, возможен только в песочнице — на сервере нет
pdfminer. Поэтому съём строк делает песочница, файл едет через дроп, а добор и сверка идут
здесь.

ГЛАВНЫЙ ЗАСЛОН — ОДНОЗНАЧНОСТЬ. Имена в СиПР идут БЕЗ организационно-правовой формы
(«А ГРУПП НСК», «АНПЗ ВНК»), и справочник на такой запрос отдаёт несколько карточек. Брать
первую нельзя: 30.07.2026 сличение строк уже слепило «Магнитогорский металлургический
комбинат» с «Комбинатом хлебопродуктов». Поэтому:
  * запрос идёт ИМЕНЕМ ВМЕСТЕ С РЕГИОНОМ — регион и есть различитель;
  * карточка принимается, только если после отсева она осталась ОДНА;
  * если карточек несколько — строка помечается «не однозначно» и остаётся БЕЗ ИНН
    (но с числом кандидатов и их ИНН в отдельной колонке — данные не выбрасываем, а
    откладываем: неоднозначный кандидат это путь к проверке, а не мусор);
  * спутники (профсоюз, садовое товарищество, фонд с именем завода внутри) отсекаются до
    подсчёта однозначности — иначе они сами создают неоднозначность на ровном месте.

КОНТРОЛЬ. Выдуманное имя «нипрятозаумень-холдинг» обязано дать 0 карточек. Если оно даёт
не 0, справочник отвечает чем попало и всем остальным ответам верить нельзя — прогон
останавливается.

Использование (с песочницы):
    python3 seo-texts/zapusk_na_servere.py seo-texts/sipr_dadata_baza.py <имя-файла-на-дропе>
"""
import csv
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

URL = 'https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party'
VYDUMANNOE_IMYA = 'нипрятозаумень-холдинг'
BAZA = r'C:\sender\_ops\PARK-BAZA-EDINAYA-3S.csv'
KATALOG = r'C:\sender\_ops'
# Формы, которые почти всегда означают «не то предприятие, а его спутник с тем же именем».
SPUTNIK = re.compile(r'профсоюз|профессиональн\w+ союз|садовод|дачн|гаражн'
                     r'|товарищество собственник|благотворит|некоммерческ\w+ партнер', re.I)


def token():
    t = os.environ.get('DADATA_TOKEN')
    if t:
        return t.strip()
    for p in (os.path.join(KATALOG, 'rs.env'), 'rs.env', 'runner-secrets.env'):
        if os.path.exists(p):
            for line in open(p, encoding='utf-8', errors='replace'):
                if line.startswith('DADATA_TOKEN'):
                    return line.split('=', 1)[1].strip().strip('"').strip()
    sys.exit('нет DADATA_TOKEN ни в окружении, ни в rs.env')


TOK = token()


def sprosit(zapros, count=5):
    telo = json.dumps({'query': zapros[:250], 'count': count}, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(URL, data=telo, headers={
        'Content-Type': 'application/json', 'Accept': 'application/json',
        'Authorization': 'Token ' + TOK})
    for popytka in range(4):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode('utf-8')).get('suggestions', [])
        except Exception as e:  # noqa: BLE001
            if popytka == 3:
                return {'oshibka': '%s: %s' % (type(e).__name__, str(e)[:120])}
            time.sleep(1.5 * (popytka + 1))
    return []


def drop_vzyat(imya):
    u = os.environ.get('DROP_URL')
    t = os.environ.get('DROP_TOKEN')
    if not u or not t:
        sys.exit('нет DROP_URL/DROP_TOKEN на сервере')
    req = urllib.request.Request(u.rstrip('/') + '/' + urllib.parse.quote(imya),
                                 headers={'X-Drop-Token': t})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def drop_polozhit(imya, b):
    u = os.environ.get('DROP_URL')
    t = os.environ.get('DROP_TOKEN')
    req = urllib.request.Request(u.rstrip('/') + '/' + urllib.parse.quote(imya), data=b,
                                 method='PUT',
                                 headers={'X-Drop-Token': t,
                                          'Content-Type': 'application/octet-stream'})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.status


def region_klyuch(s):
    """Сравнимый корень названия региона: «Челябинская область» -> «челябинск».

    Зачем так. Первая версия дописывала регион ПРЯМО В ЗАПРОС («Магнитогорский
    металлургический комбинат Челябинская область») — и справочник вернул НОЛЬ карточек
    даже на ММК. Положительный контроль это поймал сразу: отрицательный контроль дал 0
    (как и должен), а положительный тоже 0 — то есть запрос был сломан, и без второго
    контроля прогон выглядел бы как «в России нет таких предприятий». Теперь регион не
    подмешивается в строку поиска, а служит ФИЛЬТРОМ по адресу найденной карточки.
    """
    s = (s or '').lower()
    s = re.sub(r'\b(область|обл\.?|край|республика|респ\.?|автономн\w*|округ|город|г\.)\b', ' ', s)
    s = re.sub(r'[^а-яё]+', ' ', s).strip()
    slova = [re.sub(r'(ая|ий|ой|ья|ое)$', '', w) for w in s.split() if len(w) > 3]
    return ' '.join(slova)


def region_sovpal(region_sipr, karta):
    """Совпал ли регион карточки ЕГРЮЛ с регионом из СиПР."""
    a = (karta.get('data', {}).get('address') or {}).get('data') or {}
    kus = ' '.join(str(a.get(k) or '') for k in
                   ('region_with_type', 'region', 'city_with_type', 'area_with_type'))
    k1 = region_klyuch(region_sipr)
    k2 = region_klyuch(kus)
    if not k1 or not k2:
        return False
    return any(w and w in k2 for w in k1.split())


CHISTKA = re.compile(r'[«»"\'\u00ab\u00bb]')


def klyuch(s):
    """Ключ сравнения имён: без кавычек, без ОПФ, схлопнутые пробелы, строчными."""
    s = CHISTKA.sub(' ', (s or ''))
    s = re.sub(r'\b(ООО|ОАО|ПАО|ЗАО|АО|НАО|ФГУП|ГУП|МУП|АНО|ФКП|ФГБУ|ИП)\b', ' ', s, flags=re.I)
    return re.sub(r'\s+', ' ', s).strip().lower()


IMYA_V_KAVYCHKAH = re.compile(r'(?:ООО|ОАО|ПАО|ЗАО|АО|НАО|ФГУП|ГУП|МУП|АНО|ФКП|ФГБУ)?\s*'
                              r'[«"]([^«»"]{2,80})[»"]')


def pochistit_imya(s):
    """Привести имя из PDF к виду, пригодному для запроса в справочник.

    Три поправки, каждая по конкретному провалу пробного прогона на 20 строках:
      * ПЕРЕНОС ПО СЛОГАМ. В PDF «Промышлен- ный комплекс «Этана»» разорвано дефисом с
        пробелом. Справочник такого слова не знает. Склеиваем «X- Y» обратно в «XY», но
        только когда справа строчная буква: «КТК-Р» и «АЭК-Холдинг» — настоящие дефисы.
      * ВЕДУЩИЕ ПРОЧЕРКИ. Ячейка часто начинается с «– » (прочерк соседней графы).
      * ДВА ИМЕНИ В ОДНОЙ ЯЧЕЙКЕ. «ООО «АЭК- Холдинг» АО «КТК-Р» Филиал ФКП…» — это
        слипшиеся строки таблицы. Спрашиваем по ПЕРВОМУ имени в кавычках, а не по всей
        каше: иначе справочник не находит ничего и строка выглядит как несуществующее
        предприятие.
    Возвращает (имя_для_запроса, было_ли_имя_составным).
    """
    s = (s or '').strip()
    s = re.sub(r'^[\s–—-]+', '', s)
    s = re.sub(r'(\w)-\s+([а-яё])', r'\1\2', s)
    s = re.sub(r'\s+', ' ', s).strip()
    imena = IMYA_V_KAVYCHKAH.findall(s)
    if len(imena) >= 2:
        m = IMYA_V_KAVYCHKAH.search(s)
        return (m.group(0).strip() if m else imena[0]), True
    return s, False


def tochnoe_sovpadenie(imya, kandidaty):
    """Кандидаты, у которых короткое имя из ЕГРЮЛ совпадает с запросом ЗНАК В ЗНАК
    (после снятия кавычек и ОПФ). Нужно, чтобы развести однофамильцев: по «Северсталь»
    справочник отдаёт три карточки в одном регионе, и только у одной имя ровно такое."""
    k = klyuch(imya)
    if not k:
        return []
    out = []
    for c in kandidaty:
        d = c.get('data') or {}
        for pole in ((d.get('name') or {}).get('short_with_opf'),
                     (d.get('name') or {}).get('short'),
                     (d.get('name') or {}).get('full'),
                     c.get('value')):
            if pole and klyuch(pole) == k:
                out.append(c)
                break
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    imya_vhoda = sys.argv[1]
    predel = int(next((a.split('=')[1] for a in sys.argv if a.startswith('--limit=')), '100000'))

    # --- КОНТРОЛЬ ДО ВСЕГО: выдуманное имя обязано дать 0 карточек
    k = sprosit(VYDUMANNOE_IMYA)
    if isinstance(k, dict):
        sys.exit('справочник не ответил: %s' % k)
    print('КОНТРОЛЬ: выдуманное имя дало карточек %d (должно быть 0)' % len(k))
    if len(k) != 0:
        sys.exit('КОНТРОЛЬ ПРОВАЛЕН: справочник отдаёт карточки на выдуманное имя — '
                 'всем остальным ответам этого прогона верить нельзя')
    # ПОЛОЖИТЕЛЬНЫЙ контроль: заведомо существующее предприятие обязано найтись, и его
    # регион обязан пройти наш фильтр. Проверяются ОБА звена — и запрос, и фильтр региона:
    # сломано может быть любое, а снаружи и то и другое выглядит как «ничего не нашлось».
    p = sprosit('Магнитогорский металлургический комбинат')
    if isinstance(p, dict):
        sys.exit('справочник не ответил на положительный контроль: %s' % p)
    inn_mmk = p[0]['data'].get('inn') if p else None
    v_regione = [c for c in p if region_sovpal('Челябинская область', c)]
    print('КОНТРОЛЬ положительный: ММК -> карточек %d, ИНН первой %s, из них в Челябинской %d'
          % (len(p), inn_mmk, len(v_regione)))
    if not inn_mmk:
        sys.exit('КОНТРОЛЬ ПРОВАЛЕН: заведомо существующее предприятие не нашлось')
    if not v_regione:
        sys.exit('КОНТРОЛЬ ПРОВАЛЕН: фильтр региона не пропускает даже верный регион — '
                 'он отбросил бы все находки, и ноль означал бы поломку, а не отсутствие')

    # --- вход
    syr = drop_vzyat(imya_vhoda).decode('utf-8-sig')
    stroki = list(csv.DictReader(io.StringIO(syr), delimiter=';'))
    print('строк на входе: %d' % len(stroki))

    # --- наша база
    nashi_inn, nashi_imena = set(), set()
    if os.path.exists(BAZA):
        with open(BAZA, encoding='utf-8-sig', newline='') as f:
            r = csv.DictReader(f, delimiter=';')
            polya = r.fieldnames or []
            print('колонки базы (%d): %s' % (len(polya), polya[:14]))
            p_inn = [c for c in polya if re.fullmatch(r'inn|ИНН', c or '', re.I)]
            # Имя колонки НЕ угадываем: печатаем и подбираем по факту. В живой базе поле
            # называется `predpriyatie` (латиницей), и шаблон с кириллическим «предприят»
            # его не ловил — сверка по имени тихо не срабатывала бы ни разу.
            p_imya = [c for c in polya
                      if re.search(r'predpriyat|nazvanie|naimenovan|company|organiz'
                                   r'|предприят|назван', c or '', re.I)]
            print('поля базы, принятые за ИНН: %s; за наименование: %s' % (p_inn, p_imya))
            n = 0
            for row in r:
                n += 1
                for c in p_inn:
                    v = (row.get(c) or '').strip()
                    if re.fullmatch(r'\d{10}|\d{12}', v):
                        nashi_inn.add(v)
                for c in p_imya:
                    kl = klyuch(row.get(c))
                    if len(kl) > 3:
                        nashi_imena.add(kl)
            print('строк базы: %d; в ней ИНН: %d; имён: %d' % (n, len(nashi_inn), len(nashi_imena)))
    else:
        print('БАЗЫ НЕТ по пути %s — сверка не проведена' % BAZA)

    # --- добор
    kesh = {}
    out = []
    odnozn = nov = 0
    for i, s in enumerate(stroki[:predel]):
        imya = (s.get('naimenovanie') or '').strip()
        region = (s.get('region') or '').strip()
        zap = dict(s)
        # ВСЕ добавляемые поля заводим сразу: имена колонок CSV берутся из ПЕРВОЙ строки,
        # и поле, появившееся только в середине, просто не попало бы в файл — молча, без
        # ошибки. Так уже терялись данные при записи через DictWriter с extrasaction='ignore'.
        zap.update({'inn': '', 'ogrn': '', 'status_egryul': '', 'adres_egryul': '',
                    'rukovoditel': '', 'kandidatov': 0, 'kandidatov_po_imeni': 0,
                    'kandidaty_inn': '', 'razreshenie': '', 'novoe_dlya_bazy': ''})
        if len(imya) < 3:
            zap['razreshenie'] = 'имя пустое'
            out.append(zap)
            continue
        # Запрос — ТОЛЬКО именем. Регион дописывать в строку поиска нельзя (см. region_klyuch):
        # справочник на «имя + регион» отдаёт ноль даже по ММК.
        imya_zapros, sostavnoe = pochistit_imya(imya)
        zap['imya_dlya_zaprosa'] = imya_zapros
        zap['imya_sostavnoe'] = 'да' if sostavnoe else ''
        if imya_zapros in kesh:
            kand = kesh[imya_zapros]
        else:
            kand = sprosit(imya_zapros, count=10)
            if isinstance(kand, dict):
                zap['razreshenie'] = 'справочник не ответил: %s' % kand.get('oshibka', '')
                out.append(zap)
                continue
            kesh[imya_zapros] = kand
            time.sleep(0.05)
        # отсев спутников
        god = [c for c in kand if not SPUTNIK.search(c.get('value') or '')]
        zap['kandidatov_po_imeni'] = len(god)
        zap['kandidaty_inn'] = ' | '.join((c['data'].get('inn') or '') for c in god)[:200]
        # РЕГИОН — РАЗЛИЧИТЕЛЬ. Имена в СиПР без ОПФ, одноимённых юрлиц в стране много;
        # оставляем только те карточки, чей адрес в том же регионе, что и площадка в СиПР.
        v_reg = [c for c in god if region_sovpal(region, c)]
        tochnye_v_reg = tochnoe_sovpadenie(imya_zapros, v_reg)
        tochnye_vse = tochnoe_sovpadenie(imya_zapros, god)
        if len(v_reg) == 1:
            god, pometka = v_reg, 'однозначно'
        elif len(tochnye_v_reg) == 1:
            # В регионе несколько, но имя знак в знак совпадает ровно с одним — берём его.
            god, pometka = tochnye_v_reg, 'однозначно по точному имени в регионе'
        elif not v_reg and len(tochnye_vse) == 1:
            # Ни одной карточки в регионе площадки — но имя совпадает ровно с одной
            # компанией в стране. Это обычный случай федерального заказчика: ОАО «РЖД»
            # строит в Амурской области, а зарегистрировано в Москве. Отбрасывать такую
            # находку значит терять самых крупных заявителей; принимаем, но помечаем.
            god, pometka = tochnye_vse, 'однозначно по точному имени, регистрация в другом регионе'
        else:
            god, pometka = v_reg, 'однозначно'
        zap['kandidatov'] = len(god)
        if len(god) == 1:
            d = god[0]['data']
            zap.update({'inn': d.get('inn') or '',
                        'ogrn': d.get('ogrn') or '',
                        'status_egryul': ((d.get('state') or {}).get('status') or ''),
                        'adres_egryul': ((d.get('address') or {}).get('value') or '')[:200],
                        'rukovoditel': ((d.get('management') or {}).get('name') or ''),
                        'razreshenie': pometka})
            odnozn += 1
        elif len(god) == 0:
            # Различаем ДВА разных нуля: «по имени вообще ничего нет» и «по имени есть, но
            # ни одна карточка не в этом регионе». Второе — не отсутствие предприятия, а
            # отказ от догадки, и кандидаты остаются записанными в kandidaty_inn.
            zap['razreshenie'] = ('не найдено' if not zap['kandidatov_po_imeni']
                                  else 'найдено %d, но ни одна не в регионе «%s»'
                                       % (zap['kandidatov_po_imeni'], region))
        else:
            zap['razreshenie'] = 'не однозначно (%d карточек в регионе)' % len(god)
        if zap['inn']:
            zap['novoe_dlya_bazy'] = 'нет' if (zap['inn'] in nashi_inn
                                               or klyuch(imya) in nashi_imena) else 'да'
            if zap['novoe_dlya_bazy'] == 'да':
                nov += 1
        else:
            zap['novoe_dlya_bazy'] = 'не проверено (нет ИНН)' \
                if klyuch(imya) not in nashi_imena else 'нет (по имени)'
        out.append(zap)
        if (i + 1) % 50 == 0:
            print('  ...%d/%d, однозначно %d' % (i + 1, min(len(stroki), predel), odnozn))
            sys.stdout.flush()

    polya = list(out[0].keys()) if out else []
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=polya, delimiter=';', extrasaction='ignore')
    w.writeheader()
    for z in out:
        w.writerow(z)
    dannye = buf.getvalue().encode('utf-8-sig')
    imya_vyhoda = 'SIPR-ZAYAVITELI-INN.csv'
    open(os.path.join(KATALOG, imya_vyhoda), 'wb').write(dannye)
    print('на дроп: %s' % drop_polozhit(imya_vyhoda, dannye))

    s_moshch = sum(1 for z in out if (z.get('uvelichenie_MVt_chislo') or '').strip())
    s_god = sum(1 for z in out if (z.get('god_vvoda_chislo') or z.get('god_chislo') or '').strip())
    from collections import Counter
    gody = Counter((z.get('god_vvoda_chislo') or z.get('god_chislo') or '').strip()
                   for z in out)
    print('--- ИТОГ ---')
    print('строк всего: %d' % len(out))
    print('из них с мощностью: %d' % s_moshch)
    print('из них с годом ввода: %d' % s_god)
    print('ИНН найден ОДНОЗНАЧНО: %d' % odnozn)
    from collections import Counter as _C
    print('   из них по видам: %s' % sorted(_C(z['razreshenie'] for z in out if z['inn']).items()))
    print('не однозначно: %d' % sum(1 for z in out if z['razreshenie'].startswith('не однозначно')))
    print('не найдено: %d' % sum(1 for z in out if z['razreshenie'] == 'не найдено'))
    print('НОВЫХ для базы (по ИНН, из однозначных): %d' % nov)
    print('распределение по годам ввода: %s'
          % sorted((g, n) for g, n in gody.items() if g))
    print('уникальных предприятий (по ИНН): %d' % len({z['inn'] for z in out if z['inn']}))


if __name__ == '__main__':
    main()
