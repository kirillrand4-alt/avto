# -*- coding: utf-8 -*-
"""Сверка строки с ПЕРВОИСТОЧНИКОМ по четырём уровням, а не по одному.

ЗАЧЕМ ЧЕТЫРЕ, А НЕ ОДИН. Проверка «номер есть в цитате» у меня уже стоит, и она поймала одну
строку из 145. Но цитату строю я сам, и она подтверждает только то, что я аккуратно списал.
Владелец прошёлся по панели и назвал вслух остальные уровни: верно ли взято ИМЯ со страницы,
верен ли ТЕЛЕФОН, верна ли РОЛЬ, верно ли ПРЕДПРИЯТИЕ. Каждый из них ломается по-своему, и
за смену я ловил все четыре по отдельности:

    имя         «Начальник А.А.» разобрано как ФИО (у соседей), «Имя не установлено»
    телефон     ИНН физлица 773415561482 принят за номер; добавочный через пробел отрезан
    должность   «тел. (8482)» и «по пятницам с 9.00 до 12.00» записаны должностями
    роль        «Служба технического сервиса» → технический ЛПР, а человек принимает претензии
    предприятие phosagro.ru отдан как собственный сайт АО «Апатит»; sibur.ru — пяти ИНН сразу

Поэтому сверка идёт ПО СТРАНИЦЕ-ИСТОЧНИКУ, а не по моему файлу:

    1. номер       цифры номера есть в тексте страницы
    2. человек     фамилия есть в тексте страницы
    3. должность   должность есть в тексте страницы И рядом с фамилией (в пределах 300 знаков)
    4. предприятие страница принадлежит ЭТОМУ юрлицу: его ИНН в тексте, либо домен —
                   подтверждённый сайт этого ИНН, либо это карточка закупки с его ИНН

ОТДЕЛЬНО — ВТОРЫЕ РУКИ. `checko.ru`, `rusprofile`, `list-org` и прочие агрегаторы не
первоисточник: они сами откуда-то переписали, и ошибка там неотличима от факта. Такие строки
не «неверные», но и не подтверждённые — у них свой исход.

Использование:
    python3 p25_svertka_pervoistochnikov.py --predel 60 --parallel 3
"""
import csv
import glob
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import p25_hodok as hodok
import p25_nomer

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
VYHOD = os.path.join(L, 'P25-SVERKA-PERVOISTOCHNIKOV.csv')
COLS = ['inn', 'predpriyatie', 'chelovek', 'dolzhnost', 'telefon', 'vid_nomera', 'rol',
        'ssylka', 'nomer_na_stranice', 'familiya_na_stranice', 'dolzhnost_na_stranice',
        'dolzhnost_ryadom', 'predpriyatie_podtverzhdeno', 'vtorye_ruki', 'itog', 'chto_vidno']

# Агрегаторы: у них данные не свои. Это не отказ, это другой класс доверия.
VTORYE_RUKI = re.compile(r'checko\.ru|rusprofile|list-org|zachestnyibiznes|audit-it|sbis\.ru|'
                         r'testfirm|synapsenet|vbankcenter|kontragent|e-disclosure\.azipi', re.I)

SKRIPT = r"""
window.__RES = (async () => {
  const U = __URL__;
  const out = {origin: location.origin};
  // ЧИТАЕМ ТАК ЖЕ, КАК ЧИТАЛ СБОРЩИК, а не «как удобнее проверяющему». Первая версия брала
  // `innerText` отрисованной страницы и объявила ненайденными восемь строк подряд с
  // `bergauf.ru`: там контакты рисуются скриптом, и в отрисованном тексте осталось одно меню.
  // Сборщик же берёт HTML запросом и снимает теги — и людей видит. Два прибора, читающие одну
  // страницу по-разному, дают разный ответ о ней, и разошлись бы они молча: «на странице нет»
  // выглядит как факт о странице, а было фактом о способе чтения.
  let t = '';
  try {
    const r = await fetch(U, {redirect: 'follow'});
    if (r.ok) {
      const h = await r.text();
      t = h.replace(/<script[\s\S]*?<\/script>/gi, ' ').replace(/<style[\s\S]*?<\/style>/gi, ' ')
           .replace(/<[^>]+>/g, ' ').replace(/&nbsp;/gi, ' ').replace(/&amp;/gi, '&')
           .replace(/\s+/g, ' ');
    }
  } catch (e) { out.oshibka = String(e).slice(0, 70); }
  await new Promise(r => setTimeout(r, 2500));
  const vidno = document.body ? document.body.innerText : '';
  // Берём ОБА текста: что отдал сервер и что видно глазами. Человек может быть в любом.
  out.tekst = (t + ' \n ' + vidno).slice(0, 240000);
  out.dlina = out.tekst.length;
  return JSON.stringify(out);
})();
"""

def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


def chitat(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(p) else []


def familiya(s):
    ch = [x for x in re.sub(r'[^А-ЯЁа-яё -]', ' ', s or '').split() if len(x) > 3]
    bez = [x for x in ch if not re.search(r'(?:ович|евич|ьич|овна|евна|ична|инична)$', x, re.I)]
    return (bez or ch or [''])[0]


def est_nomer(cifry11, tekst):
    """Номер ищется БЕЗ КОДА СТРАНЫ и с любыми разделителями: на странице он написан как
    «8 (8202) 59-26-20», а у меня как «+7 8202592620». Сверять строки бесполезно."""
    if not cifry11 or len(cifry11) != 11:
        return False
    hvost = cifry11[1:]
    golyy = re.sub(r'\D', '', tekst)
    return hvost in golyy


def main():
    parallel = dovod('--parallel', 3)
    predel = dovod('--predel', 60)

    posl = sorted(glob.glob(os.path.join(L, 'P25-LYUDI-2S-0*.csv')))[-1]
    rows = chitat(posl)
    och = {r['inn']: r for r in chitat(os.path.join(L, 'P25-OCHERED.csv'))}
    print(f'выкладка: {os.path.basename(posl)}, строк {len(rows)}', file=sys.stderr)

    # Подтверждённые домены предприятий — для уровня 4.
    domeny = {}
    for r in chitat(os.path.join(L, 'P25-SAJTY.csv')):
        if r.get('itog') in ('подтверждён', 'название совпало'):
            d = re.sub(r'^https?://(www\.)?', '', r['sayt']).strip('/').lower()
            domeny.setdefault(r['inn'], set()).add(d)

    uzhe = {(r['inn'], r['chelovek'], r['ssylka']) for r in chitat(VYHOD)}
    # СВЕРЯЕМ ТО, ЧТО ИДЁТ В МЕРУ, А НЕ СЛУЧАЙНУЮ ВЫБОРКУ: мобильные у технических и
    # снабжения — это и есть строки, по которым продавец будет звонить.
    celi = [r for r in rows
            if r['vid_nomera'] == p25_nomer.MOBILNYY
            and r['rol'] in ('техническая', 'снабжение', 'руководство')
            and re.match(r'https?://', r['ssylka'] or '')
            and (r['inn'], r['chelovek'], r['ssylka']) not in uzhe]
    celi.sort(key=lambda r: int(och.get(r['inn'], {}).get('mesto') or 10 ** 9))
    celi = celi[:predel]
    if not celi:
        print('целей нет', file=sys.stderr)
        return

    import predel_rannera
    predel_rannera.preduprezhdenie(parallel)
    print(f'к сверке: {len(celi)}', file=sys.stderr)

    f, novyy, per, otl = hodok.dopisyvat(VYHOD, COLS)
    w = csv.DictWriter(f, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy:
        w.writeheader()
    sch = {'сверено': 0, 'всё сошлось': 0, 'вторые руки': 0, 'страница не открылась': 0,
           'номера нет': 0, 'фамилии нет': 0, 'должности нет': 0, 'предприятие не подтверждено': 0}
    lock = threading.Lock()

    def odna(r):
        js = SKRIPT.replace('__URL__', json.dumps(r['ssylka']))
        return r, hodok.vzyat(r['ssylka'], js, after_ms=3200, timeout=700)

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for n, (r, (res, kak, err)) in enumerate(pool.map(odna, celi), 1):
            with lock:
                sch['сверено'] += 1
                # PDF ЧИТАЕТСЯ НЕ ТЕКСТОМ. Первое закрытое предприятие подтверждено именно
                # документом раскрытия (`GRO_2021.pdf`), и сверщик объявил бы его несошедшимся,
                # хотя видел байты `%PDF-1.6`, а не страницу. Это ограничение прибора, и оно
                # обязано называться своим именем, а не отказом строке.
                if r['ssylka'].lower().split('?')[0].endswith('.pdf'):
                    w.writerow(dict(r, nomer_na_stranice='', familiya_na_stranice='',
                                    dolzhnost_na_stranice='', dolzhnost_ryadom='',
                                    predpriyatie_podtverzhdeno='', vtorye_ruki='',
                                    itog='PDF — этим прибором не читается',
                                    chto_vidno='источник документ, сверять надо разбором PDF'))
                    f.flush()
                    continue
                vtorye = bool(VTORYE_RUKI.search(r['ssylka']))
                if vtorye:
                    sch['вторые руки'] += 1
                if not isinstance(res, dict) or (res.get('dlina') or 0) < 200:
                    sch['страница не открылась'] += 1
                    w.writerow(dict(r, nomer_na_stranice='', familiya_na_stranice='',
                                    dolzhnost_na_stranice='', dolzhnost_ryadom='',
                                    predpriyatie_podtverzhdeno='',
                                    vtorye_ruki='да' if vtorye else '',
                                    itog='страница не открылась',
                                    chto_vidno=(err or 'пусто')[:120]))
                    f.flush()
                    continue
                t = res.get('tekst') or ''
                nizh = t.lower()
                cif = p25_nomer.razobrat(r['telefon']).cifry
                fam = familiya(r['chelovek'])
                dolzh = (r['dolzhnost'] or '').strip()

                nomer_est = est_nomer(cif, t)
                fam_est = bool(fam) and fam.lower() in nizh
                dolzh_est = bool(dolzh) and dolzh.lower()[:40] in nizh
                ryadom = ''
                if fam_est and dolzh_est:
                    i = nizh.find(fam.lower())
                    okno = nizh[max(0, i - 300):i + 300]
                    ryadom = 'да' if dolzh.lower()[:40] in okno else 'нет'

                # Уровень 4: страница принадлежит ЭТОМУ юрлицу
                host = re.sub(r'^https?://(www\.)?', '', r['ssylka']).split('/')[0].lower()
                svoy = ''
                if r['inn'] in t:
                    svoy = 'ИНН на странице'
                elif any(host.endswith(d) or d.endswith(host) for d in domeny.get(r['inn'], ())):
                    svoy = 'подтверждённый домен предприятия'
                else:
                    yad = [x for x in re.sub(r'[^0-9А-Яа-яЁёA-Za-z ]', ' ',
                                             och.get(r['inn'], {}).get('predpriyatie', '')).split()
                           if len(x) > 3 and not re.match(r'^(ООО|АО|ПАО|ОАО|ЗАО)$', x)]
                    if yad and all(x.lower() in nizh for x in yad):
                        svoy = 'название предприятия на странице'

                if not nomer_est:
                    sch['номера нет'] += 1
                if not fam_est:
                    sch['фамилии нет'] += 1
                if dolzh and not dolzh_est:
                    sch['должности нет'] += 1
                if not svoy:
                    sch['предприятие не подтверждено'] += 1

                if vtorye:
                    itog = 'вторые руки — не первоисточник'
                elif nomer_est and fam_est and (not dolzh or dolzh_est) and svoy:
                    itog = 'всё сошлось'
                    sch['всё сошлось'] += 1
                else:
                    ne = [x for x, ok in (('номер', nomer_est), ('фамилия', fam_est),
                                          ('должность', dolzh_est or not dolzh),
                                          ('предприятие', bool(svoy))) if not ok]
                    itog = 'не сошлось: ' + ', '.join(ne)

                i = nizh.find(fam.lower()) if fam_est else -1
                vidno = ' '.join(t[max(0, i - 90):i + 160].split())[:220] if i >= 0 else \
                    ' '.join(t[:160].split())
                w.writerow(dict(r, nomer_na_stranice='да' if nomer_est else 'нет',
                                familiya_na_stranice='да' if fam_est else 'нет',
                                dolzhnost_na_stranice=('да' if dolzh_est else
                                                       ('нет' if dolzh else '—')),
                                dolzhnost_ryadom=ryadom,
                                predpriyatie_podtverzhdeno=svoy or 'нет',
                                vtorye_ruki='да' if vtorye else '',
                                itog=itog, chto_vidno=vidno))
                f.flush()
                if n % 5 == 0 or n == len(celi):
                    print(f'  {n}/{len(celi)}: ' + ', '.join(f'{k} {v}' for k, v in sch.items()),
                          file=sys.stderr, flush=True)
    f.close()
    print(f'готово: {sch}\n→ {VYHOD}', file=sys.stderr)


if __name__ == '__main__':
    main()
