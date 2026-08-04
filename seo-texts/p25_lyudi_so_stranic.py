# -*- coding: utf-8 -*-
"""Страницы, найденные КАРТОЙ сайта → люди разбором ОТ ФИО. Метод №2, соединённый с методом №1.

ЧТО ЭТО ЧИНИТ. Разборщик от ФИО (`kontakty_strukturnyh_podrazdeleniy.py`) написан и работает —
на Каустике он дал 14 человек и 14 прямых номеров. Но ходит он по СПИСКУ УГАДАННЫХ ПУТЕЙ
(`PUTI`), и потому видит только сайты, устроенные как Каустик. Карта сайта (`p25_karta_sayta`)
знает настоящие адреса: на том же Каустике под фильтр подошло 328 адресов, из которых
`contacts/strukturnye-podrazdeleniya/` — первый по весу, а угадать его формой пути нельзя.

Здесь эти два звена соединены: вход — `P25-STRANICY-SAJTOV.csv` (что нашла карта), разбор —
готовый, проверенный. Своего разбора не пишу: две копии правила «ФИО, под ним должность, под
ним телефон» разошлись бы, и разошлись бы молча.

ПОЧЕМУ ТЕКСТ, А НЕ HTML. Разборщик работает по строкам видимого текста: человек, должность и
номер стоят подряд на странице, но в разметке между ними бывает по десятку тегов. Текст берётся
из браузера (`innerText`), а не вырезанием тегов регуляркой — тогда порядок строк тот же, что
видит глаз.

СЕРТИФИКАТЫ — через общий ходок `p25_hodok`, а не флагом на каждом запросе: первый заход
честный, `ignore_https_errors` только вторым и только если до сайта не дошли, путь получения
пишется полем `kak`. Без второго захода сайты на корне НУЦ Минцифры (`alrosa.ru`,
`uacrussia.ru`) отдают «Privacy error», и модуль пишет «людей нет» там, где страницу даже не
открыл.

Использование:
    python3 p25_lyudi_so_stranic.py --parallel 3 [--na-sayt 12]
"""
import csv
import json
import os
import re
import subprocess
import sys
import threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import p25_hodok as hodok
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kontakty_strukturnyh_podrazdeleniy as razbor

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
KLIENT = os.path.join(BAZA, 'server', 'run_on_server.py')
VHOD = os.path.join(L, 'P25-STRANICY-SAJTOV.csv')
VYHOD = os.path.join(L, 'P25-LYUDI-S-SAJTOV.csv')
KARTA = os.path.join(L, 'P25-lyudi-s-sajtov-zhurnal.csv')
COLS = ['inn', 'predpriyatie', 'chelovek', 'dolzhnost', 'podrazdelenie', 'telefon', 'pochta',
        'stranica', 'otkuda_stranica', 'kak', 'kontekst']

# Сколько страниц на сайт. Страницы уже отсортированы картой по весу: структурные
# подразделения и руководство идут первыми, новости — последними.
NA_SAYT = 12

SKRIPT = r"""
window.__RES = (async () => {
  const ADRESA = __ADRESA__;
  const out = [];
  for (const u of ADRESA) {
    try {
      const r = await fetch(u, {redirect: 'follow'});
      if (!r.ok) { out.push({u: u, err: 'HTTP ' + r.status}); continue; }
      const h = await r.text();
      // Разметка превращается в СТРОКИ так же, как её видит глаз: блочные теги дают перевод
      // строки, остальные — пробел. Иначе «Иванов Иван ИвановичГлавный энергетик» слипнется
      // в одну строку, и разбор от ФИО не найдёт под именем ни должности, ни номера.
      const t = h.replace(/<script[\s\S]*?<\/script>/gi, ' ')
                 .replace(/<style[\s\S]*?<\/style>/gi, ' ')
                 .replace(/<!--[\s\S]*?-->/g, ' ')
                 .replace(/<\/?(?:p|div|br|li|tr|td|th|h[1-6]|section|article|header|footer|table|ul|ol|span)\b[^>]*>/gi, '\n')
                 .replace(/<[^>]+>/g, ' ')
                 .replace(/&nbsp;/gi, ' ').replace(/&amp;/gi, '&')
                 .replace(/&quot;/gi, '"').replace(/&#0?39;|&apos;/gi, "'")
                 .replace(/[ \t ​﻿]+/g, ' ')
                 .replace(/\n\s*\n+/g, '\n');
      out.push({u: u, t: t.slice(0, 120000)});
    } catch (e) { out.push({u: u, err: String(e).slice(0, 80)}); }
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


def sprosit(sajt, adresa):
    """Через общий ходок. Здесь `__RES` — СПИСОК страниц, а не словарь, поэтому признак
    «дошли» у ходока срабатывает по непустому списку: если сайт не открылся, страниц ноль."""
    js = SKRIPT.replace('__ADRESA__', json.dumps(adresa, ensure_ascii=False))
    return hodok.vzyat(sajt + '/', js, after_ms=2000, timeout=1200)


# ЗАСЛОН «ЭТО ВООБЩЕ НАШЕ ПРЕДПРИЯТИЕ». Первый прогон положил в данные P25 37 человек с
# `kaustik.ru` — а Каустика среди 491 покупателя НЕТ, я взял его тестовым сайтом при отладке.
# Данные были настоящие и хорошие, и именно поэтому опасные: отличить их от нужных потом
# нечем, ИНН у них пустой. Строка без ИНН из очереди P25 дальше не идёт.
def nash(inn, ochered):
    return bool((inn or '').strip()) and (inn or '').strip() in ochered


def main():
    parallel = dovod('--parallel', 3)
    na_sayt = dovod('--na-sayt', NA_SAYT)
    predel = dovod('--predel', 10 ** 9)

    ochered = {r['inn'] for r in chitat(os.path.join(L, 'P25-OCHERED.csv'))}
    stranicy = chitat(VHOD)
    po_saytu = defaultdict(list)
    imena = {}
    otkuda = {}
    ne_nashi = 0
    for r in stranicy:
        s = (r.get('sayt') or '').strip()
        a = (r.get('stranica') or '').strip()
        if not s or not a:
            continue
        if not nash(r.get('inn'), ochered):
            ne_nashi += 1
            continue
        po_saytu[s].append(a)
        imena[s] = (r.get('inn', ''), r.get('predpriyatie', ''))
        otkuda[a] = r.get('otkuda', '')

    if ne_nashi:
        print(f'страниц не наших предприятий отброшено: {ne_nashi}', file=sys.stderr)
    proydeno = {r['sayt'] for r in chitat(KARTA)}
    celi = [s for s in po_saytu if s not in proydeno][:predel]
    if not celi:
        print('целей нет', file=sys.stderr)
        return

    import predel_rannera
    predel_rannera.preduprezhdenie(parallel)
    print(f'сайтов: {len(celi)}, страниц всего {sum(len(po_saytu[s]) for s in celi)}, '
          f'берём по {na_sayt} с сайта', file=sys.stderr)

    ZHCOLS = ['inn', 'sayt', 'stranic_prosili', 'stranic_otvetili', 'lyudej',
              's_telefonom', 'pochemu', 'kak']
    fv, novyy_v, per_v, otl_v = hodok.dopisyvat(VYHOD, COLS)
    fk, novyy_k, per_k, otl_k = hodok.dopisyvat(KARTA, ZHCOLS)
    for imya, per, otl in (('люди', per_v, otl_v), ('журнал', per_k, otl_k)):
        if per:
            print(f'  {imya}: шапка обновлена, перенесено строк {per}', file=sys.stderr)
        if otl:
            print(f'  {imya}: строки разной длины, {otl} отложено в *.rassoglasovan',
                  file=sys.stderr)
    wv = csv.DictWriter(fv, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy_v:
        wv.writeheader()
    wk = csv.DictWriter(fk, fieldnames=['inn', 'sayt', 'stranic_prosili', 'stranic_otvetili',
                                        'lyudej', 's_telefonom', 'pochemu'],
                        delimiter=';', extrasaction='ignore')
    if novyy_k:
        wk.writeheader()

    sch = {'сайтов': 0, 'страниц': 0, 'людей': 0, 'с телефоном': 0, 'сбоев': 0}
    lock = threading.Lock()

    def odna(s):
        return s, sprosit(s, po_saytu[s][:na_sayt])

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for n, (s, (res, kak, err)) in enumerate(pool.map(odna, celi), 1):
            with lock:
                if res is None or kak == hodok.NE_OTKRYLSYA:
                    sch['сбоев'] += 1
                    print(f'  СБОЙ {s}: {err[:110]}', file=sys.stderr, flush=True)
                    continue
                inn, predpr = imena.get(s, ('', ''))
                sch['сайтов'] += 1
                lyudej = s_tel = otvetili = 0
                vidno = set()
                for kus in res:
                    if not kus.get('t'):
                        continue
                    otvetili += 1
                    sch['страниц'] += 1
                    for ch in razbor.razobrat_stranicu(kus['t']):
                        klyuch = (ch.get('chelovek', ''), ch.get('telefon', ''))
                        if klyuch in vidno:
                            continue
                        vidno.add(klyuch)
                        lyudej += 1
                        if ch.get('telefon'):
                            s_tel += 1
                        wv.writerow({'inn': inn, 'predpriyatie': predpr,
                                     'chelovek': ch.get('chelovek', ''),
                                     'dolzhnost': ch.get('dolzhnost', ''),
                                     'podrazdelenie': ch.get('podrazdelenie', ''),
                                     'telefon': ch.get('telefon', ''),
                                     'pochta': ch.get('pochta', ''),
                                     'stranica': kus['u'],
                                     'otkuda_stranica': otkuda.get(kus['u'], ''),
                                     'kak': kak, 'kontekst': ch.get('kontekst', '')})
                sch['людей'] += lyudej
                sch['с телефоном'] += s_tel
                wk.writerow({'inn': inn, 'sayt': s,
                             'stranic_prosili': len(po_saytu[s][:na_sayt]),
                             'stranic_otvetili': otvetili, 'lyudej': lyudej,
                             's_telefonom': s_tel, 'pochemu': 'обойдено', 'kak': kak})
                fv.flush()
                fk.flush()
                print(f'  {n}/{len(celi)}: ' + ', '.join(f'{k} {v}' for k, v in sch.items()),
                      file=sys.stderr, flush=True)
    fv.close()
    fk.close()
    print(f'готово: {sch}\n→ {VYHOD}', file=sys.stderr)


if __name__ == '__main__':
    main()
