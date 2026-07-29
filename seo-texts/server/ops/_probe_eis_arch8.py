# -*- coding: utf-8 -*-
r"""ПРОБА 8: поиск по НАЗВАНИЮ вместо ИНН, привязка — по ИНН на карточке.

Итог проб 4-7: ни один штатный фильтр по заказчику в ЕИС не работает
(`customerTitle`, `customerIdOrg`, `organizationIdList` — все игнорируются и на
rss.html, и на results.html, и на обоих реестрах контрактов). Рабочим остаётся
только свободный поиск `searchString`, и по ИНН он находит компанию лишь тогда,
когда ИНН случайно попал в текст извещения: у Северстали и Уралкалия — ноль.

Название заказчика в извещении есть ВСЕГДА. Значит искать надо по названию, а
привязку доказывать ИНН на карточке — рубеж остаётся закрытым по умолчанию,
просто доказательство переезжает с запроса на проверку.

Меряем: сколько карточек находит поиск по названию и какая доля проходит рубеж.
"""
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import enrich_db as EDB       # noqa: E402

ИННЫ = ['3528000597', '5911029807', '7721632827']
ЭТАПЫ = '&fz44=on&fz223=on&af=on&ca=on&pc=on&pa=on&recordsPerPage=_50'
КОРЕНЬ = 'https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?searchString='


def кратко(имя):
    """«ПАО "СЕВЕРСТАЛЬ"» -> «СЕВЕРСТАЛЬ». Кавычки в запрос не тащим."""
    m = re.search(r'"([^"]{3,70})"', имя or '')
    s = m.group(1) if m else re.sub(
        r'^(ПУБЛИЧНОЕ\s+АКЦИОНЕРНОЕ\s+ОБЩЕСТВО|АКЦИОНЕРНОЕ\s+ОБЩЕСТВО'
        r'|ОБЩЕСТВО\s+С\s+ОГРАНИЧЕННОЙ\s+ОТВЕТСТВЕННОСТЬЮ|ПАО|АО|ООО)\s*',
        '', (имя or ''), flags=re.I)
    return re.sub(r'\s+', ' ', s).strip()[:60]


def main():
    db = EDB.EnrichDB()
    сег = datetime.now(timezone.utc).date()
    окно = ('&publishDateFrom=' + сег.replace(year=сег.year - 3).strftime('%d.%m.%Y')
            + '&publishDateTo=' + сег.strftime('%d.%m.%Y'))
    out = []
    print('НАЧАЛО проба8', flush=True)
    for inn in ИННЫ:
        r = db.cx.execute('SELECT name FROM companies WHERE inn=?', (inn,)).fetchone()
        имя = кратко(r[0] if r else '')
        з = {'inn': inn, 'запрос': имя}
        u = КОРЕНЬ + urllib.parse.quote(имя) + '&morphology=on' + ЭТАПЫ + окно
        try:
            rss = EC._eis_get(u)
        except Exception as ex:  # noqa: BLE001
            з['ошибка'] = f'{type(ex).__name__}: {str(ex)[:50]}'
            out.append(з)
            continue
        if not re.search(r'<(?:rss|channel)\b', rss or '', re.I):
            з['не_rss'] = (rss or '')[:70]
            out.append(з)
            continue
        сс = []
        for it in re.findall(r'<item>(.*?)</item>', rss, re.S):
            lm = re.search(r'<link>\s*(\S+?)\s*</link>', it, re.S)
            dm = re.search(r'<pubDate>\s*(.*?)\s*</pubDate>', it, re.S)
            if lm:
                сс.append((lm.group(1), (dm.group(1)[:16] if dm else '')))
        з['позиций'] = len(сс)
        з['даты'] = [d for _u, d in сс[:3]]
        прошло, не_прошло, люди = 0, 0, 0
        примеры = []
        # шагаем по выдаче с разбегом — не первые пять подряд одной недели
        шаг = max(1, len(сс) // 6)
        for u2, d in сс[::шаг][:6]:
            try:
                h = EC._eis_get(u2)
                t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))
            except Exception:  # noqa: BLE001
                continue
            кб = re.search(r'Контактн\w+\s+(?:информаци\w+|лиц\w+)', t, re.I)
            поз = кб.start() if кб else len(t)
            ок = inn in t[max(0, поз - 3000):поз]
            if ок:
                прошло += 1
                л = EC._eis_people(t)
                люди += len(л)
                if л and len(примеры) < 3:
                    примеры.append({'кто': л[0].get('person'),
                                    'тел': л[0].get('phone'),
                                    'почта': l0 if (l0 := л[0].get('email')) else '',
                                    'дата': d, 'url': u2[-46:]})
            else:
                не_прошло += 1
                зм = re.search(r'Заказчик\s*[:\-]?\s*([^,;]{6,60})', t)
                if len(примеры) < 6:
                    примеры.append({'ОТКЛОНЕНО_чужой_заказчик':
                                    (зм.group(1).strip() if зм else '?')[:60]})
            time.sleep(0.7)
        з.update({'прошло_рубеж': прошло, 'отклонено': не_прошло,
                  'людей_с_прошедших': люди, 'примеры': примеры})
        out.append(з)
        print('… ' + json.dumps(з, ensure_ascii=False)[:700], flush=True)
    print('ИТОГ ' + json.dumps(out, ensure_ascii=False, indent=1)[:6000], flush=True)


if __name__ == '__main__':
    main()
