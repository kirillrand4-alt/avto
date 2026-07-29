# -*- coding: utf-8 -*-
r"""ПРОБА 4: почему у крупных заказчиков поиск по ИНН отдаёт ноль или мусор.

Сухой прогон дал странное: у «Росэнергоатома» 50 позиций «актуальных», и ВСЕ
старше трёх лет, а окна за последние три года — ноль. У «Северстали» ноль
вообще. Для таких заказчиков это неправдоподобно, значит подозрение не на
архив, а на САМ ЗАПРОС: `searchString=ИНН` ищет свободным текстом по карточке
и может ловить что угодно, кроме нужного заказчика.

Сверяем на одних и тех же компаниях три параметра поиска:
  * searchString=ИНН            — как сейчас в find_zakupki_contacts;
  * customerTitle=ИНН           — штатный фильтр «заказчик» (симметричен
    supplierTitle, который в find_zakupki_supplier как раз работает);
  * customerTitle=НАЗВАНИЕ      — на случай, если по ИНН фильтр не бьётся.
И печатаем даты первых позиций: они и покажут, свежая ли это выдача.
"""
import json
import re
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import enrich_db as EDB       # noqa: E402

ИННЫ = ['7721632827', '8904034784', '3528000597', '1433000147', '5911029807']
ЭТАПЫ = '&fz44=on&fz223=on&af=on&ca=on&pc=on&pa=on&recordsPerPage=_50'
КОРЕНЬ = 'https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?'


def дат(it):
    m = re.search(r'<pubDate>\s*(.*?)\s*</pubDate>', it, re.S)
    if not m:
        return ''
    try:
        return parsedate_to_datetime(m.group(1)).astimezone(
            timezone.utc).date().isoformat()
    except Exception:  # noqa: BLE001
        return m.group(1)[:20]


def спросить(url):
    try:
        r = EC._eis_get(url)
    except Exception as ex:  # noqa: BLE001
        return {'ошибка': f'{type(ex).__name__}: {str(ex)[:50]}'}
    if not re.search(r'<(?:rss|channel)\b', r or '', re.I):
        return {'не_rss': (r or '')[:80]}
    its = re.findall(r'<item>(.*?)</item>', r, re.S)
    d = [дат(x) for x in its]
    o = {'позиций': len(its), 'даты_первых': d[:3], 'дата_последней': (d[-1] if d else '')}
    if its:
        lm = re.search(r'<link>\s*(\S+?)\s*</link>', its[0], re.S)
        o['первая_ссылка'] = (lm.group(1) if lm else '')[:95]
    return o


def main():
    db = EDB.EnrichDB()
    сег = datetime.now(timezone.utc).date()
    год_назад = сег.replace(year=сег.year - 1).strftime('%d.%m.%Y')
    out = []
    print('НАЧАЛО проба4', flush=True)
    for inn in ИННЫ:
        r = db.cx.execute('SELECT name FROM companies WHERE inn=?', (inn,)).fetchone()
        имя = (r[0] if r else '') or ''
        # короткое имя в кавычках — фильтр по названию любит именно его
        м = re.search(r'"([^"]{3,60})"', имя)
        кратко = м.group(1) if м else имя[:40]
        з = {'inn': inn, 'имя': имя[:44], 'кратко': кратко}
        з['searchString_ИНН'] = спросить(КОРЕНЬ + 'searchString=' + inn + ЭТАПЫ)
        time.sleep(0.8)
        з['customerTitle_ИНН'] = спросить(КОРЕНЬ + 'customerTitle=' + inn + ЭТАПЫ)
        time.sleep(0.8)
        з['customerTitle_имя'] = спросить(
            КОРЕНЬ + 'customerTitle=' + EC.urllib.parse.quote(кратко) + ЭТАПЫ)
        time.sleep(0.8)
        # то же с окном последнего года — работает ли фильтр дат с этим параметром
        з['customerTitle_ИНН_год'] = спросить(
            КОРЕНЬ + 'customerTitle=' + inn + ЭТАПЫ
            + '&publishDateFrom=' + год_назад
            + '&publishDateTo=' + сег.strftime('%d.%m.%Y'))
        time.sleep(0.8)
        out.append(з)
        print('… ' + json.dumps(з, ensure_ascii=False)[:600], flush=True)
    print('ИТОГ ' + json.dumps(out, ensure_ascii=False, indent=1)[:8000], flush=True)


if __name__ == '__main__':
    main()
