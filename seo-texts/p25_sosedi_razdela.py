# -*- coding: utf-8 -*-
"""Соседи по разделу: от найденной страницы отдела — ко всем остальным отделам. Добор к методу №1.

ОТКУДА ЗАДАЧА, с показанной страницы. Владелец прислал
`phosagro.ru/procurement/to-suppliers/materials-and-equipment/contacts-structure-materials-and-
equipment-department/` — «Отдел закупки технологического оборудования, техники и шин / Зайцева
Светлана Владимировна / Начальник отдела / +7 (8202) 59-33-72». Ровно тот человек, ради
которого задача. В моей карте этой страницы НЕТ. При этом её родная сестра по разделу —
`materials-and-equipment/upravlenie-skladskogo-khozyaystva/` — в карте есть, и людей с неё я
снял. То есть в раздел я попал, а по разделу не прошёлся.

ПОЧЕМУ КАРТА ЕЁ НЕ ВЗЯЛА. Карта строится из `sitemap.xml` и меню главной. Страницы отделов
внутри раздела закупок в карту сайта не попадают (их там просто нет), а в меню главной стоит
раздел, а не его листья. Найти их можно только одним способом: открыть страницу раздела и
прочитать её ссылки. Догадаться формой пути нельзя — `contacts-structure-materials-and-
equipment-department` не выводится ни из чего.

ЧТО БЕРЁТСЯ ЗА ТОЧКУ ВХОДА. Страницы с весом 0–4 (структура, руководство, сотрудники,
контакты, отделы) И ИХ РОДИТЕЛЬСКИЕ ПУТИ. Родитель нужен отдельно: у ФосАгро найденная
страница — лист, а список всех отделов лежит на `materials-and-equipment/`, то есть ВЫШЕ
неё. Без подъёма на уровень вверх соседи не видны.

ЧЕГО МОДУЛЬ НЕ ДЕЛАЕТ. Не разбирает людей и не ходит вглубь дальше одного шага. Его ответ —
новые адреса с пометкой `откуда=сосед по разделу`; разбор их подберёт метод №2 обычным ходом.
Один шаг, а не обход всего сайта: цена ошибки в глубину — тысячи страниц каталога товаров.

Использование:
    python3 p25_sosedi_razdela.py --parallel 3 [--predel 40]
"""
import csv
import json
import os
import re
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import p25_hodok as hodok
import p25_karta_sayta as karta

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
STRANICY = os.path.join(L, 'P25-STRANICY-SAJTOV.csv')
ZHURNAL = os.path.join(L, 'P25-sosedi-zhurnal.csv')
COLS = ['inn', 'predpriyatie', 'sayt', 'stranica', 'otkuda', 'zagolovok', 'kak']
ZHCOLS = ['inn', 'sayt', 'vhodov', 'ssylok_vsego', 'podoshlo', 'novyh', 'kak', 'pochemu']

# Сколько страниц-входов на сайт. Вход стоит один запрос, а даёт весь список отделов.
VHODOV = 8
VES_VHODA = 4      # 0–4: структура, руководство, сотрудники, контакты, отделы
NOVYH_NA_SAYT = 25

SKRIPT = r"""
window.__RES = (async () => {
  const VHODY = __VHODY__;
  const SAJT = location.origin, host = location.host;
  const pochinit = (u) => {
    try { const a = new URL(u, SAJT);
      if (a.protocol === 'http:' && a.host === host) a.protocol = 'https:';
      a.hash = ''; return a.href; } catch (e) { return null; }
  };
  const out = [];
  for (const v of VHODY) {
    try {
      const r = await fetch(v, {redirect: 'follow'});
      if (!r.ok) { out.push({v: v, err: 'HTTP ' + r.status}); continue; }
      const h = await r.text();
      const ssylki = [];
      // Заголовок ссылки забирается вместе с адресом: по нему вес считается точнее, чем по
      // пути. «/procurement/to-suppliers/mte/» ни о чём не говорит, а подпись «Отдел закупки
      // технологического оборудования» говорит всё.
      for (const m of h.matchAll(/<a[^>]+href=["']([^"'#]+)["'][^>]*>([\s\S]{0,160}?)<\/a>/gi)) {
        const a = pochinit(m[1]);
        if (!a) continue;
        try { if (new URL(a).host !== host) continue; } catch (e) { continue; }
        const t = m[2].replace(/<[^>]+>/g, ' ').replace(/&nbsp;/gi, ' ')
                      .replace(/\s+/g, ' ').trim();
        ssylki.push({a: a, t: t.slice(0, 120)});
      }
      out.push({v: v, ssylki: ssylki.slice(0, 600)});
    } catch (e) { out.push({v: v, err: String(e).slice(0, 80)}); }
  }
  return JSON.stringify(out);
})();
"""


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


def chitat(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(p) else []


def roditel(u):
    """`.../materials-and-equipment/upravlenie-skladskogo-khozyaystva/` →
    `.../materials-and-equipment/`. Корень сайта родителем не считается: он и так обойден."""
    p = urlparse(u)
    kuski = [k for k in p.path.split('/') if k]
    if len(kuski) < 2:
        return ''
    return f'{p.scheme}://{p.netloc}/' + '/'.join(kuski[:-1]) + '/'


def vhody(adresa):
    """Точки входа: СНАЧАЛА все родители, потом сами страницы.

    Порядок именно такой, и это проверено на ФосАгро. Если брать вперемешку («родитель,
    страница, родитель, страница»), то первые шесть мест занимают три страницы со словом
    `management` в пути и их родители, а `procurement/to-suppliers/materials-and-equipment/` —
    тот самый раздел, где лежат отделы закупок с людьми, — не помещается. Родитель ценнее
    листа всегда: лист мы уже видели, а родитель — это список ВСЕХ его братьев.
    """
    horoshie = [a for a in adresa if karta.ves_adresa(a, '') <= VES_VHODA]
    horoshie.sort(key=lambda x: (karta.ves_adresa(x, ''), len(x)))
    ryad, vidno = [], set()
    for beryom_roditelya in (True, False):
        for a in horoshie:
            kand = roditel(a) if beryom_roditelya else a
            if kand and kand not in vidno:
                vidno.add(kand)
                ryad.append(kand)
    return ryad[:VHODOV]


def main():
    parallel = dovod('--parallel', 3)
    predel = dovod('--predel', 10 ** 9)

    ochered = {r['inn'] for r in chitat(os.path.join(L, 'P25-OCHERED.csv'))}
    po_saytu = defaultdict(list)
    imena = {}
    for r in chitat(STRANICY):
        s = (r.get('sayt') or '').strip()
        a = (r.get('stranica') or '').strip()
        inn = (r.get('inn') or '').strip()
        if not s or not a or inn not in ochered:
            continue
        po_saytu[s].append(a)
        imena[s] = (inn, r.get('predpriyatie', ''))

    proydeno = {r['sayt'] for r in chitat(ZHURNAL)}
    celi = [s for s in po_saytu if s not in proydeno and vhody(po_saytu[s])][:predel]
    if not celi:
        print('целей нет', file=sys.stderr)
        return

    import predel_rannera
    predel_rannera.preduprezhdenie(parallel)
    print(f'сайтов: {len(celi)}', file=sys.stderr)

    izvestno = defaultdict(set)
    for s, ad in po_saytu.items():
        izvestno[s] = set(ad)

    fs, novyy_s, per_s, _ = hodok.dopisyvat(STRANICY, COLS)
    fz, novyy_z, per_z, _ = hodok.dopisyvat(ZHURNAL, ZHCOLS)
    ws = csv.DictWriter(fs, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy_s:
        ws.writeheader()
    wz = csv.DictWriter(fz, fieldnames=ZHCOLS, delimiter=';', extrasaction='ignore')
    if novyy_z:
        wz.writeheader()

    sch = {'сайтов': 0, 'входов': 0, 'новых страниц': 0, 'сбоев': 0}
    lock = threading.Lock()

    def odin(s):
        v = vhody(po_saytu[s])
        js = SKRIPT.replace('__VHODY__', json.dumps(v, ensure_ascii=False))
        return s, v, hodok.vzyat(s + '/', js, after_ms=2000, timeout=1200)

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for n, (s, v, (res, kak, err)) in enumerate(pool.map(odin, celi), 1):
            with lock:
                inn, predpr = imena.get(s, ('', ''))
                if res is None or kak == hodok.NE_OTKRYLSYA:
                    sch['сбоев'] += 1
                    wz.writerow({'inn': inn, 'sayt': s, 'vhodov': len(v), 'ssylok_vsego': 0,
                                 'podoshlo': 0, 'novyh': 0, 'kak': kak,
                                 'pochemu': (err or 'не дошли')[:120]})
                    fz.flush()
                    continue
                sch['сайтов'] += 1
                vsego = podoshlo = novyh = 0
                for kus in res:
                    if not isinstance(kus, dict) or not kus.get('ssylki'):
                        continue
                    sch['входов'] += 1
                    for x in kus['ssylki']:
                        a, t = x.get('a', ''), x.get('t', '')
                        vsego += 1
                        if not a or karta.MUSOR.search(a) or karta.YAZYKI.match(a):
                            continue
                        # Заголовок ссылки — равноправный довод наравне с путём: имя отдела
                        # стоит в подписи чаще, чем в адресе.
                        if not (karta.NUZHNO.search(a) or karta.NUZHNO.search(t)):
                            continue
                        podoshlo += 1
                        if a in izvestno[s] or novyh >= NOVYH_NA_SAYT:
                            continue
                        izvestno[s].add(a)
                        novyh += 1
                        ws.writerow({'inn': inn, 'predpriyatie': predpr, 'sayt': s,
                                     'stranica': a, 'otkuda': 'сосед по разделу',
                                     'zagolovok': t, 'kak': kak})
                sch['новых страниц'] += novyh
                wz.writerow({'inn': inn, 'sayt': s, 'vhodov': len(v), 'ssylok_vsego': vsego,
                             'podoshlo': podoshlo, 'novyh': novyh, 'kak': kak,
                             'pochemu': 'обойдено'})
                fs.flush()
                fz.flush()
                print(f'  {n}/{len(celi)}: ' + ', '.join(f'{k} {x}' for k, x in sch.items()),
                      file=sys.stderr, flush=True)
    fs.close()
    fz.close()
    print(f'готово: {sch}\n→ {STRANICY}', file=sys.stderr)


if __name__ == '__main__':
    main()
