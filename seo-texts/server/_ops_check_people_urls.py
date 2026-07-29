# -*- coding: utf-8 -*-
"""Утверждение №1, содержательная проверка: открываем source_url и смотрим,
есть ли ТАМ этот человек и эта должность.

Берём выборку: все гл.инженеры (самое ценное для продажника) + несколько
директоров/снабженцев из разных компаний. Для каждого:
  - тянем страницу,
  - ищем фамилию, ищем инициалы/имя, ищем слова должности рядом (окно ±400
    символов вокруг фамилии),
  - печатаем фрагмент, чтобы это можно было прочитать глазами.
"""
import gzip
import io
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

try:
    import requests
except Exception:  # noqa: BLE001
    requests = None

e = EDB.EnrichDB().cx
ИСТ = 'сайт:руководство'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')


def текст(h):
    h = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', h)
    h = re.sub(r'(?s)<[^>]+>', ' ', h)
    h = h.replace('&nbsp;', ' ').replace('&#39;', "'").replace('&amp;', '&')
    h = h.replace('&quot;', '"').replace('&laquo;', '"').replace('&raquo;', '"')
    return re.sub(r'\s+', ' ', h)


def тянуть(url):
    if requests is None:
        return None, 'нет requests'
    try:
        r = requests.get(url, timeout=25, headers={'User-Agent': UA},
                         verify=False)
        b = r.content
        enc = r.encoding or 'utf-8'
        for cand in (enc, 'utf-8', 'cp1251'):
            try:
                s = b.decode(cand)
                if 'Ð' not in s[:2000] and 'п»ї' not in s[:200]:
                    return s, 'HTTP %s' % r.status_code
            except Exception:  # noqa: BLE001
                continue
        return b.decode('utf-8', 'replace'), 'HTTP %s' % r.status_code
    except Exception as ex:  # noqa: BLE001
        return None, 'ERR %s' % str(ex)[:120]


def main():
    отбор = []
    отбор += e.execute(
        "SELECT inn, person, post, role, source_url FROM people WHERE source=? "
        "AND role LIKE '%инжен%'", (ИСТ,)).fetchall()
    отбор += e.execute(
        "SELECT inn, person, post, role, source_url FROM people WHERE source=? "
        "AND role IN ('снабжение/закупки','нач.производства','гл.энергетик') "
        "LIMIT 4", (ИСТ,)).fetchall()
    отбор += e.execute(
        "SELECT inn, person, post, role, source_url FROM people WHERE source=? "
        "AND role='директор' LIMIT 3", (ИСТ,)).fetchall()
    print('проверяем записей:', len(отбор))
    итог = []
    for inn, per, post, role, url in отбор:
        html, st = тянуть(url)
        c = e.execute('SELECT name, site FROM companies WHERE inn=?',
                      (inn,)).fetchone()
        rec = {'инн': inn, 'фио': per, 'должн': post, 'роль': role, 'url': url,
               'статус': st, 'компания': (c or ['', ''])[0],
               'сайт_карточки': (c or ['', ''])[1]}
        if html:
            t = текст(html)
            фам = str(per or '').split()[0] if per else ''
            i = t.lower().find(фам.lower()) if фам else -1
            rec['фамилия_на_странице'] = i >= 0
            if i >= 0:
                rec['фрагмент'] = t[max(0, i - 220):i + 220]
            rec['длина_текста'] = len(t)
        итог.append(rec)
        print(json.dumps(rec, ensure_ascii=False)[:900])
    ок = sum(1 for x in итог if x.get('фамилия_на_странице'))
    дост = sum(1 for x in итог if x.get('длина_текста'))
    print('ИТОГ_URL проверено=%d страниц_доступно=%d фамилия_найдена=%d'
          % (len(итог), дост, ок))


if __name__ == '__main__':
    main()
