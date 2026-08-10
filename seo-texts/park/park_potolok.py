# -*- coding: utf-8 -*-
"""Сколько ЗАПИСЕЙ ЕИС отдаёт по общим запросам — то есть каков потолок канала.
Одна страница на запрос, читаем только счётчик «Результаты поиска N записей»."""
import json, os, re, time, urllib.parse
BAZA = r'C:\sender'
OUT = os.path.join(BAZA, 'park_potolok.jsonl')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
ZAPROSY = ['винтовой компрессор', 'поршневой компрессор', 'центробежный компрессор',
           'воздушный компрессор', 'компрессорная установка', 'компрессорная станция',
           'компрессор', 'воздуходувка', 'газодувка', 'турбокомпрессор', 'нагнетатель',
           'осушитель сжатого воздуха', 'ресивер воздушный', 'ресивер сжатого воздуха',
           'генератор азота', 'азотная станция', 'генератор кислорода', 'кислородная станция',
           'воздухоразделительная установка', 'модульная компрессорная станция',
           'передвижная компрессорная станция', 'дизельная компрессорная станция',
           'винтовой блок', 'компрессорное оборудование', 'сжатый воздух']
def _hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e): return e
    return None
def main():
    itog = []
    from playwright.sync_api import sync_playwright
    exe = _hrom()
    with sync_playwright() as p:
        kw = {'headless': True, 'args': ['--no-sandbox', '--disable-blink-features=AutomationControlled']}
        if exe: kw['executable_path'] = exe
        br = p.chromium.launch(**kw)
        ctx = br.new_context(user_agent=UA, locale='ru-RU', viewport={'width': 1366, 'height': 900},
                             ignore_https_errors=True)
        page = ctx.new_page()
        for q in ZAPROSY:
            u = ('https://zakupki.gov.ru/epz/order/extendedsearch/results.html?searchString=%s'
                 '&morphology=on&pageNumber=1&recordsPerPage=_50&fz44=on&fz223=on&af=on&ca=on&pc=on&pa=on'
                 % urllib.parse.quote(q))
            r = {'zapros': q}
            try:
                otv = page.goto(u, timeout=60000, wait_until='domcontentloaded')
                page.wait_for_timeout(3000)
                t = re.sub(r'\s+', ' ', page.inner_text('body'))
                r['http'] = otv.status if otv else None
                m = re.search(r'Результаты поиска\s*([\d\s]{1,12})\s*записей', t)
                r['zapisey'] = int(re.sub(r'\D', '', m.group(1))) if m else None
            except Exception as e:
                r['oshibka'] = str(e)[:140]
            itog.append(r)
            with open(OUT, 'a', encoding='utf-8') as f:
                f.write(json.dumps(r, ensure_ascii=False) + '\n'); f.flush(); os.fsync(f.fileno())
        br.close()
    print(json.dumps(itog, ensure_ascii=False))
if __name__ == '__main__':
    main()
