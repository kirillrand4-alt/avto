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


CHISTKA = re.compile(r'[«»"\'\u00ab\u00bb]')


def klyuch(s):
    """Ключ сравнения имён: без кавычек, без ОПФ, схлопнутые пробелы, строчными."""
    s = CHISTKA.sub(' ', (s or ''))
    s = re.sub(r'\b(ООО|ОАО|ПАО|ЗАО|АО|НАО|ФГУП|ГУП|МУП|АНО|ФКП|ФГБУ|ИП)\b', ' ', s, flags=re.I)
    return re.sub(r'\s+', ' ', s).strip().lower()


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
    # и положительный контроль: заведомо существующее предприятие обязано найтись
    p = sprosit('Магнитогорский металлургический комбинат Челябинская область')
    inn_mmk = p[0]['data'].get('inn') if p and not isinstance(p, dict) else None
    print('КОНТРОЛЬ положительный: ММК -> карточек %d, ИНН первой %s'
          % (len(p) if not isinstance(p, dict) else -1, inn_mmk))
    if not inn_mmk:
        sys.exit('КОНТРОЛЬ ПРОВАЛЕН: заведомо существующее предприятие не нашлось')

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
            p_imya = [c for c in polya
                      if re.search(r'nazvanie|naimenovan|company|organiz|предприят|назван',
                                   c or '', re.I)]
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
        zap.update({'inn': '', 'ogrn': '', 'status_egryul': '', 'adres_egryul': '',
                    'rukovoditel': '', 'kandidatov': 0, 'kandidaty_inn': '',
                    'razreshenie': '', 'novoe_dlya_bazy': ''})
        if len(imya) < 3:
            zap['razreshenie'] = 'имя пустое'
            out.append(zap)
            continue
        kl = (imya, region)
        if kl in kesh:
            kand = kesh[kl]
        else:
            kand = sprosit('%s %s' % (imya, region))
            if isinstance(kand, dict):
                zap['razreshenie'] = 'справочник не ответил: %s' % kand.get('oshibka', '')
                out.append(zap)
                continue
            kesh[kl] = kand
            time.sleep(0.05)
        # отсев спутников
        god = [c for c in kand if not SPUTNIK.search(c.get('value') or '')]
        zap['kandidatov'] = len(god)
        zap['kandidaty_inn'] = ' | '.join((c['data'].get('inn') or '') for c in god)[:200]
        if len(god) == 1:
            d = god[0]['data']
            zap.update({'inn': d.get('inn') or '',
                        'ogrn': d.get('ogrn') or '',
                        'status_egryul': ((d.get('state') or {}).get('status') or ''),
                        'adres_egryul': ((d.get('address') or {}).get('value') or '')[:200],
                        'rukovoditel': ((d.get('management') or {}).get('name') or ''),
                        'razreshenie': 'однозначно'})
            odnozn += 1
        elif len(god) == 0:
            zap['razreshenie'] = 'не найдено'
        else:
            zap['razreshenie'] = 'не однозначно (%d карточек)' % len(god)
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
    print('не однозначно: %d' % sum(1 for z in out if z['razreshenie'].startswith('не однозначно')))
    print('не найдено: %d' % sum(1 for z in out if z['razreshenie'] == 'не найдено'))
    print('НОВЫХ для базы (по ИНН, из однозначных): %d' % nov)
    print('распределение по годам ввода: %s'
          % sorted((g, n) for g, n in gody.items() if g))
    print('уникальных предприятий (по ИНН): %d' % len({z['inn'] for z in out if z['inn']}))


if __name__ == '__main__':
    main()
