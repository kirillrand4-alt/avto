#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Снимки страниц предпросмотра: как статья ляжет на сайте.

    python3 snimki.py [--shirina 1280] [--out snimki]

Смотрит браузером, а не разбором разметки: горизонтальная прокрутка,
вылезшая таблица и неотличимый от текста призыв видны только глазом.
Заодно СЧИТАЕТ то, что глазом мерить неточно - реальную ширину блоков,
цвет фона призыва, размер кнопки.
"""
import argparse
import glob
import json
import os

DIR = os.path.dirname(os.path.abspath(__file__))

ZAMER = """() => {
  const vyvod = {shirinaBody: document.body.scrollWidth,
                 shirinaOkna: document.documentElement.clientWidth,
                 shire: []};
  document.querySelectorAll('table, pre, img, div, p').forEach(el => {
    if (el.scrollWidth > document.documentElement.clientWidth + 2) {
      vyvod.shire.push({teg: el.tagName, klass: (el.className||'').slice(0,40),
                        shirina: el.scrollWidth});
    }
  });
  const cta = document.querySelector('p.cta');
  if (cta) {
    const s = getComputedStyle(cta);
    vyvod.cta = {fon: s.backgroundColor, otstup: s.paddingLeft,
                 zhirnost: s.fontWeight, liniya: s.borderLeftWidth};
  }
  const knopka = document.querySelector('.cta-knopka a');
  if (knopka) {
    const s = getComputedStyle(knopka);
    const r = knopka.getBoundingClientRect();
    vyvod.knopka = {fon: s.backgroundColor, cvet: s.color,
                    shirina: Math.round(r.width), vysota: Math.round(r.height),
                    ramka: s.borderStyle, radius: s.borderRadius,
                    otstup: s.paddingTop + ' ' + s.paddingLeft};
  }
  const ogl = document.querySelector('p.na-stranice');
  if (ogl) vyvod.oglavlenie = {fon: getComputedStyle(ogl).backgroundColor};
  vyvod.tablic = document.querySelectorAll('table').length;
  vyvod.knopok = document.querySelectorAll('.cta-knopka a').length;
  return vyvod;
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--shirina', type=int, default=1280)
    ap.add_argument('--vysota', type=int, default=2400)
    ap.add_argument('--out', default=os.path.join(DIR, 'snimki'))
    ap.add_argument('--vhod', default=os.path.join(DIR, 'predprosmotr'))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    from playwright.sync_api import sync_playwright
    zamery = {}
    with sync_playwright() as pw:
        # Путь к бинарнику ищем сами: playwright в этом окружении помнит
        # версию, которой нет, и падает с советом «playwright install»,
        # хотя браузер на месте под другим номером сборки.
        kand = sorted(glob.glob('/opt/pw-browsers/chromium*/chrome-linux/chrome'))
        br = pw.chromium.launch(executable_path=kand[-1] if kand else None)
        for put in sorted(glob.glob(os.path.join(a.vhod, '*', '*.html'))):
            dom = os.path.basename(os.path.dirname(put))
            slug = os.path.basename(put)[:-5]
            stranica = br.new_page(viewport={'width': a.shirina, 'height': a.vysota})
            try:
                stranica.goto('file://' + os.path.abspath(put), wait_until='load', timeout=45000)
                stranica.wait_for_timeout(1200)
                z = stranica.evaluate(ZAMER)
                snimok = os.path.join(a.out, f'{dom}__{slug}.png')
                stranica.screenshot(path=snimok, full_page=True)
                z['snimok'] = os.path.basename(snimok)
                zamery[f'{dom}/{slug}'] = z
                bok = z['shirinaBody'] - z['shirinaOkna']
                print(f'{dom:26} прокрутка вбок {bok:+5}  таблиц {z.get("tablic",0):2} '
                      f'кнопок {z.get("knopok",0):2}  призыв-фон {z.get("cta",{}).get("fon","НЕТ")}')
            except Exception as e:
                print(f'{dom:26} ОШИБКА {e}')
            finally:
                stranica.close()
        br.close()
    with open(os.path.join(a.out, 'zamery.json'), 'w', encoding='utf-8') as f:
        json.dump(zamery, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
