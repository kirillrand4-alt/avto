#!/usr/bin/env python3
"""Скриншоты доноров: посмотреть площадку глазами, а не по разметке.

Съём через сервер (browser_probe с дельфин-профилями) 18.08 вернул по всем 15
доменам «WinError 10061: target machine actively refused it» - Dolphin Anty на
сервере не запущен. Эти доноры краул не блокировали, поэтому смотрим их
предустановленным Chromium из песочницы: главная + профильный раздел.

    python3 shots.py eyes-15.txt
"""
import json, os, sys
from playwright.sync_api import sync_playwright

OUT = 'shots'
EXEC = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'


def main():
    doms = [l.strip() for l in open(sys.argv[1], encoding='utf-8') if l.strip()]
    verd = {x['dom']: x for x in json.load(open('final-donors-checked.json', encoding='utf-8'))}
    raw = json.load(open('topic-raw.json', encoding='utf-8'))
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        br = p.chromium.launch(args=['--no-sandbox'], executable_path=EXEC)
        for d in doms:
            ctx = br.new_context(viewport={'width': 1280, 'height': 1400},
                                 locale='ru-RU', ignore_https_errors=True)
            pg = ctx.new_page()
            urls = [f'https://{d}/']
            # профильный раздел, который назвала классификация
            sect = (verd.get(d) or {}).get('section', '')
            for s in (raw.get(d) or {}).get('sections', []):
                if sect and sect.strip('#').lower()[:12] in s['text'].lower():
                    urls.append(s['url']); break
            for i, u in enumerate(urls):
                try:
                    pg.goto(u, timeout=45000, wait_until='domcontentloaded')
                    pg.wait_for_timeout(3500)
                    pg.screenshot(path=f'{OUT}/{d}{"" if not i else "-razdel"}.png',
                                  full_page=False)
                    print(f'  {d:24} {"главная" if not i else "раздел "} ok', flush=True)
                except Exception as e:                       # noqa: BLE001
                    print(f'  {d:24} {u[:40]} ОШИБКА {repr(e)[:70]}', flush=True)
            ctx.close()
        br.close()


if __name__ == '__main__':
    main()
