# -*- coding: utf-8 -*-
"""Выгрузка реестра заключений ЭПБ с monitor-pb.ru в CSV.

Зачем. Заключение ЭПБ делают на оборудование, которое **выработало назначенный срок
службы**: это не «когда-то купили», а зарегистрированный государством факт, что машина
работает на продлении и у продления есть дата конца. Фильтр `validity=expiring`
(«истекает в ближайшие 12 месяцев») — это и есть окно замены, датированное ведомством.

Что даёт строка: ИНН заказчика, точная модель с заводским и инвентарным номером, регион,
экспертная организация, вывод, ссылка на карточку. ФИО в реестре НЕТ — ни заказчика, ни
(в открытой части) экспертов; человека добираем другими способами по ИНН.

Использование:
    python3 mpb_harvest.py "центробежный компрессор" expiring out.csv
    python3 mpb_harvest.py "компрессор" expiring out.csv --max-pages 40

Поиск на сайте — полнотекстовый со стеммингом, несколько слов соединяются по И.
Внимание: «компрессор» и «компрессорная» — разные леммы, покрытие набирается
несколькими запросами.
"""
import csv
import html
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = 'https://monitor-pb.ru'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
PAUSE = 1.5  # сервис публичный и бесплатный — не долбим


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode('utf-8', 'replace')


def total(page):
    m = re.search(r'Показано[^Р]{0,80}из\s*([\d\s  ]+)', _text(page))
    return int(re.sub(r'\D', '', m.group(1))) if m else 0


def _text(h):
    t = re.sub(r'<script.*?</script>', '', h, flags=re.S)
    t = re.sub(r'<style.*?</style>', '', t, flags=re.S)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', t))


ROW = re.compile(r'<tr>(.*?)</tr>', re.S)


def rows(page):
    """Разобрать строки таблицы результатов."""
    out = []
    for chunk in ROW.findall(page):
        m_num = re.search(r'href="/conclusion/([^"]+)"[^>]*>([^<]+)<', chunk)
        if not m_num:
            continue
        m_cust = re.search(r'href="/customer/(\d+)"[^>]*>(.*?)</a>', chunk, re.S)
        m_org = re.search(r'href="/org/(\d+)"[^>]*>(.*?)</a>', chunk, re.S)
        m_org_noinn = re.search(r'</td><td class="break-words">(?!<a)(.*?)</td>', chunk, re.S)
        m_date = re.search(r'>(\d{2}\.\d{2}\.\d{4})<', chunk)
        # кавычки внутри title экранированы как &quot;, поэтому [^"]* безопасно и
        # не даёт ленивому .*? уползти в соседнюю кнопку «Скопировать номер»
        m_obj = re.search(r'<button type="button" title="([^"]*)" aria-expanded', chunk)
        m_type = re.search(r'class="font-mono">([А-Я]{2})<', chunk)
        m_verd = re.search(r'text-xs font-medium[^>]*>([^<]+)</span>', chunk)
        cust_name = html.unescape(re.sub(r'<[^>]+>', '', m_cust.group(2))).strip() if m_cust else ''
        org_name = (html.unescape(re.sub(r'<[^>]+>', '', m_org.group(2))).strip() if m_org
                    else (html.unescape(re.sub(r'<[^>]+>', '', m_org_noinn.group(1))).strip()
                          if m_org_noinn else ''))
        out.append({
            'nomer': html.unescape(m_num.group(2)).strip(),
            'data': m_date.group(1) if m_date else '',
            'inn_zakazchika': m_cust.group(1) if m_cust else '',
            'zakazchik': cust_name,
            'obekt': re.sub(r'\s+', ' ', html.unescape(m_obj.group(1))).strip() if m_obj else '',
            'tip': m_type.group(1) if m_type else '',
            'inn_eo': m_org.group(1) if m_org else '',
            'ekspertnaya_org': org_name,
            'vyvod': html.unescape(m_verd.group(1)).strip() if m_verd else '',
            'istochnik': f'{BASE}/conclusion/{m_num.group(1)}',
            'istochnik_zakazchik': (f'{BASE}/customer/{m_cust.group(1)}' if m_cust else ''),
        })
    return out


def main():
    if len(sys.argv) < 4:
        sys.exit('usage: mpb_harvest.py <запрос> <active|expiring|expired|any> <out.csv> '
                 '[--max-pages N]')
    q, validity, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    max_pages = 400
    if '--max-pages' in sys.argv:
        max_pages = int(sys.argv[sys.argv.index('--max-pages') + 1])

    qs = {'q': q}
    if validity != 'any':
        qs['validity'] = validity
    url0 = f'{BASE}/conclusions?{urllib.parse.urlencode(qs)}'
    first = get(url0)
    n = total(first)
    print(f'запрос «{q}», срок={validity}: {n} заключений', file=sys.stderr)

    seen, recs = set(), []
    page_html, p = first, 1
    while p <= max_pages:
        got = rows(page_html)
        new = [r for r in got if r['nomer'] not in seen]
        for r in new:
            seen.add(r['nomer'])
        recs.extend(new)
        print(f'  стр. {p}: строк {len(got)}, новых {len(new)}, всего {len(recs)}/{n}',
              file=sys.stderr)
        if len(recs) >= n or not got:
            break
        p += 1
        qs['page'] = p
        time.sleep(PAUSE)
        try:
            page_html = get(f'{BASE}/conclusions?{urllib.parse.urlencode(qs)}')
        except Exception as e:  # noqa: BLE001
            print(f'  стр. {p} не открылась: {e}', file=sys.stderr)
            break

    cols = ['nomer', 'data', 'inn_zakazchika', 'zakazchik', 'obekt', 'tip',
            'inn_eo', 'ekspertnaya_org', 'vyvod', 'istochnik', 'istochnik_zakazchik']
    with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';')
        w.writeheader()
        w.writerows(recs)
    inns = {r['inn_zakazchika'] for r in recs if r['inn_zakazchika']}
    print(f'записано {len(recs)} строк, уникальных ИНН заказчиков: {len(inns)} -> {out_path}',
          file=sys.stderr)


if __name__ == '__main__':
    main()
