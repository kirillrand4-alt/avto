#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Машинная приёмка вёрстки: все страницы, обе ширины, ноль моделей.

    python3 priyomka.py [--vhod predprosmotr-vse] [--out priyomka.json]

ЧТО ЭТО ЗАКРЫВАЕТ. Осмотр глазами нужен для вкуса и связности, но
половину списка проверок машина делает точнее и по ВСЕЙ сетке, а не
по выборке: контраст надписи к фону считается по формуле, а не «на глаз
читается», размер кнопки под палец меряется в пикселях, вылет за экран
ловится сравнением ширин.

ПОЧЕМУ КОНТРАСТ СЧИТАЕТСЯ, А НЕ ОЦЕНИВАЕТСЯ. Кнопка abac шла белым
по жёлтому - отношение 1,9:1, надпись фактически невидима. Глазом на
снимке это спорно («вроде видно»), формулой WCAG - однозначно.
"""
import argparse
import glob
import json
import os

DIR = os.path.dirname(os.path.abspath(__file__))

ZAMER = r"""() => {
  const d = document, okno = d.documentElement.clientWidth;
  const cvet = s => {
    const m = s.match(/[\d.]+/g) || [0,0,0];
    return [+m[0], +m[1], +m[2], m.length > 3 ? +m[3] : 1];
  };
  // Яркость по WCAG: канал в линейное пространство, затем взвешенная сумма.
  const yark = ([r,g,b]) => {
    const f = v => { v /= 255; return v <= .03928 ? v/12.92 : Math.pow((v+.055)/1.055, 2.4); };
    return .2126*f(r) + .7152*f(g) + .0722*f(b);
  };
  const kontrast = (a, b) => {
    const l1 = yark(a), l2 = yark(b);
    return (Math.max(l1,l2) + .05) / (Math.min(l1,l2) + .05);
  };
  // Фон элемента: ищем ближайшего непрозрачного предка.
  const fon = el => {
    let u = el;
    while (u) {
      const c = cvet(getComputedStyle(u).backgroundColor);
      if (c[3] > .5) return c;
      u = u.parentElement;
    }
    return [255,255,255,1];
  };

  const vyvod = {bok: d.body.scrollWidth - okno, okno, knopki: [], plashki: [],
                 shire: [], zazory: [], pustye: 0};

  d.querySelectorAll('.cta-knopka a').forEach(a => {
    const r = a.getBoundingClientRect(), s = getComputedStyle(a);
    vyvod.knopki.push({
      w: Math.round(r.width), h: Math.round(r.height),
      kontrast: +kontrast(cvet(s.color), fon(a)).toFixed(2),
      nadpis: (a.textContent || '').trim().slice(0, 30),
      href: a.getAttribute('href') || '',
      vidna: r.width > 20 && r.height > 12
    });
  });

  d.querySelectorAll('p.cta').forEach(p => {
    const s = getComputedStyle(p);
    vyvod.plashki.push({
      // насколько плашка отличается от фона под ней
      otlichie: +kontrast(cvet(s.backgroundColor), fon(p.parentElement)).toFixed(2),
      liniya: parseFloat(s.borderLeftWidth) || 0
    });
  });

  d.querySelectorAll('table, img, pre').forEach(el => {
    if (el.getBoundingClientRect().width > okno + 2) {
      const ob = el.closest('.tablica-prokrutka');
      vyvod.shire.push({teg: el.tagName, obernut: !!ob});
    }
  });

  // Нулевой зазор между блоками: заголовок, прилипший к таблице или тексту.
  const bloki = [...d.querySelectorAll('h2, h3, table, p.cta, .tablica-prokrutka')];
  for (let i = 0; i < bloki.length - 1; i++) {
    const a = bloki[i].getBoundingClientRect(), b = bloki[i+1].getBoundingClientRect();
    if (bloki[i].contains(bloki[i+1]) || bloki[i+1].contains(bloki[i])) continue;
    const z = Math.round(b.top - a.bottom);
    if (z >= 0 && z < 6) vyvod.zazory.push({posle: bloki[i].tagName, do: bloki[i+1].tagName, z});
  }

  d.querySelectorAll('p, td, th, h2, h3').forEach(el => {
    if (!el.textContent.trim() && !el.querySelector('img')) vyvod.pustye++;
  });

  const h2 = d.querySelector('h2'), h3 = d.querySelector('h3');
  if (h2 && h3) {
    vyvod.kegli = {h2: parseFloat(getComputedStyle(h2).fontSize),
                   h3: parseFloat(getComputedStyle(h3).fontSize)};
  }
  const ogl = d.querySelector('p.na-stranice');
  if (ogl) vyvod.oglavlenie = {vysota: Math.round(ogl.getBoundingClientRect().height),
                               punktov: ogl.querySelectorAll('a').length};
  // Якорь, которого нет на странице
  vyvod.bityeYakorya = [...d.querySelectorAll('a[href^="#"]')]
    .filter(a => !d.getElementById(a.getAttribute('href').slice(1))).length;
  return vyvod;
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vhod', default=os.path.join(DIR, 'predprosmotr-vse'))
    ap.add_argument('--out', default=os.path.join(DIR, 'priyomka.json'))
    a = ap.parse_args()

    from playwright.sync_api import sync_playwright
    kand = sorted(glob.glob('/opt/pw-browsers/chromium*/chrome-linux/chrome'))
    itog = {}
    fajly = sorted(glob.glob(os.path.join(a.vhod, '*', '*.html')))
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=kand[-1] if kand else None)
        for shirina, imya in ((1280, 'nastolnaya'), (390, 'telefon')):
            for i, put in enumerate(fajly, 1):
                slug = os.path.basename(put)[:-5]
                st = br.new_page(viewport={'width': shirina, 'height': 1000})
                try:
                    st.goto('file://' + os.path.abspath(put), wait_until='load', timeout=45000)
                    st.wait_for_timeout(350)
                    itog.setdefault(slug, {})[imya] = st.evaluate(ZAMER)
                except Exception as e:
                    itog.setdefault(slug, {})[imya] = {'oshibka': str(e)[:120]}
                finally:
                    st.close()
                if i % 25 == 0:
                    print(f'{imya}: {i}/{len(fajly)}', flush=True)
        br.close()
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(itog, f, ensure_ascii=False)
    print(f'проверено страниц: {len(itog)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
