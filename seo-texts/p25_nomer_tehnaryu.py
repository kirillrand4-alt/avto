# -*- coding: utf-8 -*-
"""Добрать ЛИЧНЫЙ МОБИЛЬНЫЙ конкретному техническому человеку на сайте его же предприятия.

ЗАЧЕМ ИМЕННО ЭТО И ИМЕННО СЕЙЧАС. Мера ТЗ — предприятие закрыто, когда есть технический ЛПР
с личным мобильным. Замер на живой выкладке:

    людей всего                                804
    с личным мобильным                         117
    с технической должностью                    12
    техническая должность И личный мобильный     0   ← мера
    из 12 технических: с городским номером       4, с мобильным 0

То есть не хватает не людей и не номеров по отдельности, а их встречи. Двенадцать человек —
это весь список, отделяющий нас от первого закрытого предприятия, и по каждому известно
ровно одно: чего именно недостаёт.

ПОЧЕМУ НА САЙТЕ, А НЕ ПОИСКОМ. Прямой поиск по имени закрыт капчей (`yandex.ru/search`
ответил «подтвердите, что запросы отправляли вы»), а xmlriver наружу отдаёт только новости и
домен. Зато сайт предприятия у нас теперь есть у 342 из 491, и страница этого сайта —
первоисточник по определению ТЗ, в отличие от агрегатора.

ЧЕМ ОТЛИЧАЕТСЯ ОТ ОБЩЕГО РАЗБОРА СТРАНИЦ. Тот идёт ОТ ФИО и берёт всех подряд. Здесь
наоборот: фамилия известна заранее, и ищется она — с потолком страниц втрое выше, потому что
цена одного такого человека равна целому предприятию в мере успеха.

ЧТО СЧИТАЕТСЯ НАХОДКОЙ. Мобильный (11 цифр с 7/8 и второй 9, либо 10 с первой 9) в пределах
окна от фамилии, и **окно небольшое**: близость не доказывает принадлежность, но чем ближе,
тем меньше шанс, что это номер соседа по списку. Цитата сохраняется дословно — по ней видно,
чей это номер, и решение принимает человек, а не модуль.

Использование:
    python3 p25_nomer_tehnaryu.py [--parallel 3] [--stranic 40]
"""
import csv
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import p25_hodok as hodok

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
# ОТДЕЛЬНЫЙ ФАЙЛ, А НЕ ОБЩИЙ С КАНАЛОМ ВЫДАЧИ. Оба модуля искали номер одному и тому же
# человеку и дописывали в `P25-NOMERA-TEHNARYAM.csv` — но шапки у них РАЗНЫЕ
# (`nayden_nomer`/`vid_nomera`/`stranica` против `nomer`/`vid`/`zapros`). Строки съехали на
# колонку: у закрытого предприятия в поле цитаты оказалась ссылка, а вид номера уехал в поле
# запроса. Проверить такую строку нечем, а выглядит она полной.
VYHOD = os.path.join(L, 'P25-NOMERA-S-SAJTA.csv')
COLS = ['inn', 'predpriyatie', 'chelovek', 'dolzhnost', 'nayden_nomer', 'vid_nomera',
        'stranica', 'kak', 'citata']

SKRIPT = r"""
window.__RES = (async () => {
  const ADRESA = __ADRESA__;
  const FAM = __FAM__;
  const out = [];
  for (const u of ADRESA) {
    try {
      const r = await fetch(u, {redirect: 'follow'});
      if (!r.ok) continue;
      const h = await r.text();
      const t = h.replace(/<script[\s\S]*?<\/script>/gi, ' ')
                 .replace(/<style[\s\S]*?<\/style>/gi, ' ')
                 .replace(/<\/?(?:p|div|br|li|tr|td|th|h[1-6]|section|article|span|table)\b[^>]*>/gi, '\n')
                 .replace(/<[^>]+>/g, ' ').replace(/&nbsp;/gi, ' ')
                 .replace(/[ \t]+/g, ' ').replace(/\n\s*\n+/g, '\n');
      let i = t.indexOf(FAM);
      while (i >= 0) {
        out.push({u: u, kusok: t.slice(Math.max(0, i - 200), i + 400)});
        if (out.length >= 12) break;
        i = t.indexOf(FAM, i + 1);
      }
      if (out.length >= 12) break;
    } catch (e) { /* страница не открылась — это не находка и не ошибка человека */ }
  }
  return JSON.stringify(out);
})();
"""

MOB = re.compile(r'(?:\+?7|8)[\s\-()]*9\d{2}[\s\-()]*\d{3}[\s\-]?\d{2}[\s\-]?\d{2}')
GOR = re.compile(r'(?:\+?7|8)[\s\-()]*\d{3,5}[\s\-()]*\d{2,3}[\s\-]?\d{2}[\s\-]?\d{2}')


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


def chitat(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(p) else []


def familiya(s):
    ch = re.sub(r'[^А-ЯЁа-яё -]', ' ', s or '').split()
    return ch[0] if ch else ''


def main():
    parallel = dovod('--parallel', 3)
    stranic = dovod('--stranic', 40)

    import glob
    posl = sorted(glob.glob(os.path.join(L, 'P25-LYUDI-2S-0*.csv')))[-1]
    lyudi = chitat(posl)
    teh = [x for x in lyudi if x.get('rol') == 'техническая']
    # Мобильный уже есть — цель достигнута, второй раз не ищем.
    teh = [x for x in teh if not MOB.search(x.get('telefon') or '')]

    stranicy = {}
    for r in chitat(os.path.join(L, 'P25-STRANICY-SAJTOV.csv')):
        stranicy.setdefault(r['inn'], []).append(r['stranica'])
    sajty = {}
    for r in chitat(os.path.join(L, 'P25-SAJTY.csv')):
        if r['itog'] in ('подтверждён', 'название совпало'):
            sajty.setdefault(r['inn'], r['sayt'])

    celi = []
    for x in teh:
        adresa = stranicy.get(x['inn'], [])
        if not adresa:
            continue
        celi.append((x, sajty.get(x['inn']) or adresa[0].split('/')[0] + '//'
                     + adresa[0].split('/')[2], adresa[:stranic]))
    print(f'технических без мобильного: {len(teh)}, из них с известными страницами: {len(celi)}',
          file=sys.stderr)
    if not celi:
        print('целей нет — у этих людей не найдено страниц их предприятия', file=sys.stderr)
        return

    import predel_rannera
    predel_rannera.preduprezhdenie(parallel)

    fv, novyy, per, otl = hodok.dopisyvat(VYHOD, COLS)
    w = csv.DictWriter(fv, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy:
        w.writeheader()
    sch = {'людей': 0, 'найден мобильный': 0, 'найден городской': 0, 'фамилии нет': 0,
           'сбоев': 0}
    lock = threading.Lock()

    def odin(c):
        x, sajt, adresa = c
        fam = familiya(x['chelovek'])
        js = (SKRIPT.replace('__ADRESA__', json.dumps(adresa, ensure_ascii=False))
              .replace('__FAM__', json.dumps(fam, ensure_ascii=False)))
        res, kak, err = hodok.vzyat(sajt + '/', js, after_ms=2000, timeout=1200)
        return c, res, kak, err

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for n, (c, res, kak, err) in enumerate(pool.map(odin, celi), 1):
            x = c[0]
            with lock:
                sch['людей'] += 1
                if res is None or kak == hodok.NE_OTKRYLSYA:
                    sch['сбоев'] += 1
                    print(f'  СБОЙ {x["chelovek"][:22]}: {err[:80]}', file=sys.stderr, flush=True)
                    continue
                if not res:
                    sch['фамилии нет'] += 1
                    continue
                nashli = False
                for kus in res:
                    t = kus.get('kusok') or ''
                    m = MOB.search(t)
                    vid = 'личный мобильный' if m else ''
                    if not m:
                        m = GOR.search(t)
                        vid = 'городской' if m else ''
                    if not m:
                        continue
                    nashli = True
                    sch['найден мобильный' if vid == 'личный мобильный'
                        else 'найден городской'] += 1
                    w.writerow({'inn': x['inn'], 'predpriyatie': x.get('predpriyatie', ''),
                                'chelovek': x['chelovek'], 'dolzhnost': x.get('dolzhnost', ''),
                                'nayden_nomer': m.group(0).strip(), 'vid_nomera': vid,
                                'stranica': kus.get('u', ''), 'kak': kak,
                                'citata': ' '.join(t.split())[:400]})
                    if vid == 'личный мобильный':
                        break
                if not nashli:
                    sch['фамилии нет'] += 1
                fv.flush()
                print(f'  {n}/{len(celi)}: ' + ', '.join(f'{a} {b}' for a, b in sch.items()),
                      file=sys.stderr, flush=True)
    fv.close()
    print(f'готово: {sch}\n→ {VYHOD}', file=sys.stderr)


if __name__ == '__main__':
    main()
