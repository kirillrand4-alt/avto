# -*- coding: utf-8 -*-
"""Контакты с ПОДТВЕРЖДЁННОГО сайта предприятия: почта, телефон, человек с должностью.

ЗАЧЕМ ОТДЕЛЬНЫЙ МОДУЛЬ, А НЕ `p25_lyudi_so_stranic`. Тот берёт вход из
`P25-STRANICY-SAJTOV.csv` (снятая карта сайта) и отбрасывает всё, чего нет в
`P25-OCHERED.csv` — очереди из 25 верхних покупателей. Предприятия парка машин в этой
очереди не стоят, значит готовый модуль отбросил бы их все до единого и отчитался «людей
нет». Здесь тот же разбор от ФИО (`kontakty_strukturnyh_podrazdeleniy.razobrat_stranicu`) —
своей копии правила не пишу, — но карта снимается на лету и очередь другая.

ЧТО СЧИТАЕТСЯ НАХОДКОЙ. Только то, что видно НА СТРАНИЦЕ САЙТА предприятия, со ссылкой на
эту страницу и цитатой вокруг находки. Строка без ссылки не пишется вовсе: пустое поле
честнее придуманного, а находка без первоисточника — это и есть придуманное.

КАЖДЫЙ ИСТОЧНИК — СВОЯ СТРОКА. Склейка «три почты через запятую, ссылка одна» теряет
ровно то, ради чего собиралось: какую из трёх видно на какой странице.

СЕРТИФИКАТЫ И КОДИРОВКА — через общий ходок `p25_hodok`: первый заход честный, флаг только
вторым; кодировка берётся из заголовка и из <meta>, иначе windows-1251 приезжает
кракозябрами и разбор от ФИО не находит на странице ни одного человека.

Использование:
    python3 p25_kontakty_park.py --vhod <csv inn;predpriyatie;sayt> [--parallel 3]
                                 [--stranic 10] [--predel 500] [--vyhod <csv>]
"""
import csv
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import p25_hodok as hodok
import kontakty_strukturnyh_podrazdeleniy as razbor

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
VYHOD = os.path.join(L, 'PARK-KONTAKTY-2S.csv')
ZHURNAL = os.path.join(L, 'PARK-KONTAKTY-2S-zhurnal.csv')
COLS = ['inn', 'predpriyatie', 'sayt', 'chto_naydeno', 'znachenie', 'chelovek', 'dolzhnost',
        'ssylka', 'citata']
COLS_ZH = ['inn', 'sayt', 'stranic_prosili', 'stranic_otvetili', 'pocht', 'telefonov',
           'lyudey', 'kak', 'pochemu']

STRANIC = 10

# Адреса, где контакты живут на самом деле. Список нарочно широкий: цена лишнего адреса —
# один запрос, цена пропущенного — предприятие, закрытое как «контактов нет».
NUZHNO = re.compile(r'contact|kontakt|svyaz|rekvizit|struktur|podrazdelen|rukovod|management|'
                    r'team|about|o-kompanii|o-nas|o-predpriyatii|o-zavode|company|upravlen|'
                    r'otdel|sluzhb|personal|sotrudnik|komanda|administrac|press|sbyt|prodazh|'
                    r'zakup|snabzhen|postavshchik|partner|vacanc|vakans', re.I)
MUSOR = re.compile(r'\.(?:jpg|jpeg|png|gif|svg|pdf|docx?|xlsx?|pptx?|zip|rar|mp4|css|js)(?:$|\?)'
                   r'|/rss|\?PAGEN|/page/\d|/tags?/|/search|/bitrix/|/upload/|/local/|'
                   r'/login|/auth|/basket|/cart|mailto:|tel:', re.I)
YAZYKI = re.compile(r'^https?://[^/]+/(?:en|eng|de|fr|es|cn|zh|it|tr)(?:/|$)', re.I)

# Вес адреса: чем меньше, тем раньше обходим. Реквизиты и контакты — раньше новостей.
VES = [
    (re.compile(r'strukturn|podrazdelen|otdel|sluzhb|upravlen|apparat', re.I), 0),
    (re.compile(r'rukovod|management|team|komanda|administrac|personal|sotrudnik', re.I), 1),
    (re.compile(r'contact|kontakt|svyaz', re.I), 2),
    (re.compile(r'rekvizit', re.I), 3),
    (re.compile(r'sbyt|prodazh|zakup|snabzhen|postavshchik|partner', re.I), 4),
    (re.compile(r'about|o-kompanii|o-nas|o-predpriyatii|o-zavode|company', re.I), 5),
    (re.compile(r'press|vacanc|vakans', re.I), 7),
]

SKRIPT = r"""
window.__RES = (async () => {
  const SAJT = location.origin;
  const host = location.host;
  const SKOLKO = __SKOLKO__;
  const pochinit = (u) => {
    try { const a = new URL(u, SAJT);
      if (a.protocol === 'http:' && a.host === host) a.protocol = 'https:';
      a.hash = ''; return a.href; } catch (e) { return null; }
  };
  // КОДИРОВКА БЕРЁТСЯ СО СТРАНИЦЫ, А НЕ ПРЕДПОЛАГАЕТСЯ: `r.text()` декодирует в UTF-8, и
  // сайт на windows-1251 приезжает кракозябрами. Тогда разбор от ФИО честно скажет «людей
  // нет» — и это будет факт о способе чтения, а не о странице.
  const dostat = async (u) => {
    try {
      const r = await fetch(u, {redirect: 'follow'});
      if (!r.ok) return null;
      const buf = await r.arrayBuffer();
      let kod = ((r.headers.get('content-type') || '').toLowerCase()
                 .match(/charset=([\w-]+)/) || [])[1] || '';
      if (!kod) {
        const nachalo = new TextDecoder('latin1').decode(buf.slice(0, 2048)).toLowerCase();
        kod = (nachalo.match(/charset=["']?([\w-]+)/) || [])[1] || 'utf-8';
      }
      try { return new TextDecoder(kod).decode(buf); }
      catch (e) { return new TextDecoder('utf-8').decode(buf); }
    } catch (e) { return null; }
  };
  // Разметка в СТРОКИ так, как её видит глаз: блочные теги дают перевод строки. Иначе
  // «Иванов Иван ИвановичГлавный энергетик» слипнется, и разбор от ФИО не найдёт должности.
  const v_tekst = (h) => (h || '')
      .replace(/<script[\s\S]*?<\/script>/gi, ' ').replace(/<style[\s\S]*?<\/style>/gi, ' ')
      .replace(/<!--[\s\S]*?-->/g, ' ')
      .replace(/<\/?(?:p|div|br|li|tr|td|th|h[1-6]|section|article|header|footer|table|ul|ol|span|dt|dd)\b[^>]*>/gi, '\n')
      .replace(/<[^>]+>/g, ' ')
      .replace(/&nbsp;/gi, ' ').replace(/&amp;/gi, '&').replace(/&quot;/gi, '"')
      .replace(/&#0?39;|&apos;/gi, "'").replace(/&laquo;/gi, '«').replace(/&raquo;/gi, '»')
      .replace(/[ \t ​﻿]+/g, ' ').replace(/\n\s*\n+/g, '\n');

  const out = {origin: SAJT, stranicy: []};
  const glav = await dostat(SAJT + '/');
  if (glav === null) { out.oshibka = 'главная не открылась'; return JSON.stringify(out); }
  out.stranicy.push({u: SAJT + '/', t: v_tekst(glav).slice(0, 150000)});
  // MAILTO И TEL ИЗ РАЗМЕТКИ ГЛАВНОЙ — отдельная добыча, а не побочный шум: почта в
  // атрибуте href есть там, где в видимом тексте она нарисована картинкой.
  out.mailto = [];
  for (const m of glav.matchAll(/mailto:([^"'?>\s]+)/gi))
    if (!out.mailto.includes(m[1])) out.mailto.push(m[1]);
  const adresa = [];
  for (const m of glav.matchAll(/<a[^>]+href=["']([^"'#]+)["']/gi)) {
    const a = pochinit(m[1]);
    if (!a) continue;
    try { if (new URL(a).host !== host) continue; } catch (e) { continue; }
    if (!adresa.includes(a)) adresa.push(a);
  }
  out.vsego_ssylok = adresa.length;
  out.otobrano = __ADRESA__(adresa);
  for (const u of out.otobrano.slice(0, SKOLKO)) {
    const h = await dostat(u);
    if (h === null) { out.stranicy.push({u: u, err: 'не открылась'}); continue; }
    const mt = [];
    for (const m of h.matchAll(/mailto:([^"'?>\s]+)/gi))
      if (!mt.includes(m[1])) mt.push(m[1]);
    out.stranicy.push({u: u, t: v_tekst(h).slice(0, 150000), mailto: mt});
  }
  return JSON.stringify(out);
})();
"""

# Отбор адресов сделан НА СТОРОНЕ СТРАНИЦЫ, но правило одно с питоновским: подставляется
# готовая функция, чтобы два списка «что считать контактной страницей» не разошлись молча.
OTBOR_JS = r"""((adresa) => {
  // Выражения строятся ИЗ СТРОК, а не подставляются в литерал `/.../`: в шаблонах есть
  // косая черта (`^https?://`), и литерал на ней рвётся посреди выражения — разбор падает
  // молча, а страница возвращает пустой список адресов, что выглядит как «на сайте нет
  // контактных страниц».
  const NUZHNO = new RegExp(__NUZHNO__, 'i'), MUSOR = new RegExp(__MUSOR__, 'i'),
        YAZYKI = new RegExp(__YAZYKI__, 'i');
  const VES = __VES__;
  const ves = (a) => { for (const [r, v] of VES) if (new RegExp(r, 'i').test(a)) return v;
                       return 9; };
  return adresa.filter((a) => NUZHNO.test(a) && !MUSOR.test(a) && !YAZYKI.test(a))
               .sort((x, y) => ves(x) - ves(y) || x.length - y.length);
})"""

POCHTA = re.compile(r'\b[A-Za-z0-9._%+-]{2,}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
TEL = re.compile(r'(?:\+7|\b8)[\s\-–()]*\(?\d{3,5}\)?[\s\-–]*\d{2,3}[\s\-–]*'
                 r'\d{2}[\s\-–]*\d{2}\b')
# Реквизит рядом с числом — не телефон: «ИНН 7802 04 88 30» разбирается шаблоном телефона
# один в один. Тот же заслон, что в сборщике Тендер.Про.
NE_TEL = re.compile(r'(?:ИНН|ОГРН|ОКПО|КПП|БИК|р/с|к/с|счёт|счет|лиценз|№)\D{0,6}$', re.I)
POCHTA_MUSOR = re.compile(r'@(?:example|domain|mail\.example|sentry|w3\.org|schema\.org|'
                          r'your(?:site|domain)|site\.ru|test\.|localhost|'
                          r'\d+\.\d+|.*\.(?:png|jpg|gif|svg|css|js))', re.I)
POCHTA_IMYA_MUSOR = re.compile(r'^(?:noreply|no-reply|donotreply|postmaster|abuse|webmaster@)',
                               re.I)
# ТРИ СЛОВА С БОЛЬШОЙ БУКВЫ — ЕЩЁ НЕ ЧЕЛОВЕК. Шаблон ФИО в разборе требует ровно этого, и на
# `kr-evrz.ru` он выдал человека по имени «Красноярский Электровагоноремонтный Завод» —
# строку названия предприятия со страницы. Ошибка не шумит: имя настоящее, страница
# настоящая, цитата настоящая, — просто это не человек, а завод. Признак человека, который
# заводу не подделать, — ОТЧЕСТВО: русское отчество кончается на -ович/-евич/-ична/-овна и
# так далее. Требую его хотя бы у одного из трёх слов.
OTCHESTVO = re.compile(r'(?:ович|евич|ьич|иевич|овна|евна|ична|инична|кызы|оглы|улы)$', re.I)
# Слова, которых в имени человека не бывает: если они есть — разобрана строка названия.
NE_IMYA = re.compile(r'\b(?:завод|комбинат|общество|ооо|оао|пао|зао|ао|предприяти|группа|'
                     r'компани|филиал|управлени|центр|больниц|поликлиник|институт|'
                     r'университет|техникум|фабрик|объединени|корпораци|холдинг|служб|'
                     r'департамент|отдел|цех|участок|станци|район|область|республик|город)',
                     re.I)

# РОЛЬ РЕШАЕТ, НУЖЕН ЛИ НАМ ЭТОТ ЧЕЛОВЕК. Больница с медицинским воздухом законно стоит в
# списке владельцев компрессора, но врач-оториноларинголог к его закупке отношения не имеет.
# Роли берём технические и снабженческие, плюс приёмную как запасной вход.
# СТРОКИ НЕ ВЫБРАСЫВАЮТСЯ, А ПОМЕЧАЮТСЯ: «страница разобрана, человек не нашей роли» — это
# факт о человеке, а «строки нет» читалось бы как «страницу не смотрели».
NASHA_ROL = re.compile(
    r'глав\w*\s*\.?\s*(?:инженер|энергетик|механик|метролог|технолог)'
    r'|техническ\w+\s+директор|директор\s+по\s+(?:техни|производств|эксплуатац|развити)'
    r'|зам\w*\s*\.?\s*(?:директора\s+по\s+техни|глав\w*\s*\.?\s*инженер)'
    r'|начальник\w*\s+(?:отдела\s+|службы\s+|управления\s+)?'
    r'(?:огм|огэ|компрессорн|энергоцех|энергетическ|механическ|ремонтн|'
    r'снабжен|закуп|мто|материально|технич)'
    r'|инженер\s+по\s+(?:эксплуатац|оборудован|надзор|промышленн\w+\s+безопасн|энергетик)'
    r'|(?:отдел|служб|управлени|департамент|дирекци)\w*\s+(?:по\s+)?'
    r'(?:снабжен|закуп|мто|материально[- ]техническ)'
    r'|снабжен|закупк|тендерн|приёмная|приемная|энергетик|механик|энергослужб', re.I)
# ЛЕЧЕБНАЯ ДОЛЖНОСТЬ ОТМЕНЯЕТ СОВПАДЕНИЕ. «Заведующий приемным отделением» больницы попал в
# наши роли по слову «приемн» — а это не приёмная предприятия, а отделение скорой помощи.
# Поэтому «приёмная» засчитывается только целым словом, а медицина отменяет любое совпадение.
NE_NASHA_YAVNO = re.compile(r'врач|медицин|медсестр|фельдшер|педиатр|хирург|терапевт|'
                            r'стоматолог|ларинголог|невролог|акушер|санитар|'
                            r'учител|воспитател|преподавател|бухгалтер|юрист|кадр', re.I)
NE_NASHA_ROL = 'человек не нашей роли'


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


def chitat(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(p) else []


def sobrat_js(skolko):
    import json as _j
    otbor = (OTBOR_JS.replace('__NUZHNO__', _j.dumps(NUZHNO.pattern))
             .replace('__MUSOR__', _j.dumps(MUSOR.pattern))
             .replace('__YAZYKI__', _j.dumps(YAZYKI.pattern))
             .replace('__VES__', _j.dumps([[r.pattern, v] for r, v in VES])))
    return SKRIPT.replace('__ADRESA__', otbor).replace('__SKOLKO__', str(int(skolko)))


def citata(tekst, poz, dlina, okno=110):
    a = max(0, poz - okno)
    b = min(len(tekst), poz + dlina + okno)
    return re.sub(r'\s+', ' ', tekst[a:b]).strip()[:300]


def nomer_cifrovoy(s):
    c = re.sub(r'\D', '', s)
    if len(c) == 11 and c[0] in '78':
        return '+7' + c[1:]
    if len(c) == 10:
        return '+7' + c
    return ''


def razobrat(tekst, mailto):
    """Страница → находки. Каждая несёт СВОЮ позицию, чтобы цитата была именно вокруг неё."""
    nahodki = []
    vidno = set()
    ne_lyudi = []
    for m in POCHTA.finditer(tekst or ''):
        e = m.group(0).strip().strip('.').lower()
        if POCHTA_MUSOR.search(e) or POCHTA_IMYA_MUSOR.match(e) or e in vidno:
            continue
        vidno.add(e)
        nahodki.append(('почта', e, '', '', citata(tekst, m.start(), len(m.group(0)))))
    for e in (mailto or []):
        e = (e or '').strip().lower()
        if not POCHTA.fullmatch(e) or POCHTA_MUSOR.search(e) \
                or POCHTA_IMYA_MUSOR.match(e) or e in vidno:
            continue
        vidno.add(e)
        nahodki.append(('почта', e, '', '', 'ссылка mailto: в разметке страницы'))
    for m in TEL.finditer(tekst or ''):
        if NE_TEL.search(tekst[max(0, m.start() - 24):m.start()]):
            continue
        n = nomer_cifrovoy(m.group(0))
        if not n or n in vidno:
            continue
        vidno.add(n)
        nahodki.append(('телефон', n, '', '', citata(tekst, m.start(), len(m.group(0)))))
    for ch in razbor.razobrat_stranicu(tekst or ''):
        imya = (ch.get('chelovek') or '').strip()
        dolzh = (ch.get('dolzhnost') or '').strip()
        if not imya or not dolzh:
            continue          # человек без должности для этой задачи не находка
        if NE_IMYA.search(imya) or not any(OTCHESTVO.search(w) for w in imya.split()):
            ne_lyudi.append(imya)
            continue          # это строка названия, а не человек
        if ('чел', imya) in vidno:
            continue
        vidno.add(('чел', imya))
        # ЦИТАТА ЦЕНТРИРУЕТСЯ НА САМОЙ НАХОДКЕ, а не берётся окном строк вокруг неё. Готовый
        # `kontekst` разборщика начинается за две строки ДО имени, и на странице-списке там
        # стоит хвост ПРЕДЫДУЩЕГО человека: у одной строки цитата открывалась чужой почтой
        # `platno@crbvolhov.ru`. Проверяющий видит несовпадение и перестаёт верить всей
        # строке — хотя сама находка верна. Цитата обязана показывать контекст ЭТОГО контакта.
        # ИМЯ НА СТРАНИЦЕ ВСТРЕЧАЕТСЯ НЕ ОДИН РАЗ: в списке людей, в меню, в подписи к
        # новости. Первое вхождение — не обязательно то, где стоит его должность, и цитата
        # тогда показывает соседей по списку вместо него самого. Берём то вхождение, рядом с
        # которым стоит ЕГО ЖЕ должность: именно эту пару и проверяет глазами человек.
        mesta_i = [m.start() for m in re.finditer(re.escape(imya), tekst or '')]
        i = -1
        for p in mesta_i:
            if dolzh and dolzh[:40] in (tekst or '')[max(0, p - 220):p + 220]:
                i = p
                break
        if i < 0 and mesta_i:
            i = mesta_i[0]
        # ЦИТАТА ОТКРЫВАЕТСЯ БЛОКОМ САМОГО ЧЕЛОВЕКА, а не хвостом предыдущего. Симметричное
        # окно вокруг имени честно, но читается плохо: слева стоит чужая почта, и проверяющий
        # видит несовпадение раньше, чем совпадение. Начало берём от его собственной
        # должности, если она стоит перед именем (вёрстка «должность → имя → телефон»), иначе
        # от имени, и тянем вправо — там его контакты.
        nachalo = i
        if i >= 0 and dolzh:
            p = (tekst or '').rfind(dolzh[:40], max(0, i - 220), i)
            if p >= 0:
                nachalo = p
        kon = re.sub(r'\s+', ' ', (tekst or '')[nachalo:nachalo + 300]).strip() \
            if i >= 0 else re.sub(r'\s+', ' ', (ch.get('kontekst') or '')).strip()[:300]
        if not kon:
            continue          # цитата обязательна: без неё строка не пишется
        rod = ('человек' if NASHA_ROL.search(dolzh) and not NE_NASHA_YAVNO.search(dolzh)
               else NE_NASHA_ROL)
        nahodki.append((rod, imya, imya, dolzh, kon))
        for pole, chto in (('telefon', 'телефон человека'), ('pochta', 'почта человека')):
            v = (ch.get(pole) or '').strip()
            if not v:
                continue
            v = nomer_cifrovoy(v) if pole == 'telefon' else v.lower()
            if not v or (chto, v, imya) in vidno:
                continue
            vidno.add((chto, v, imya))
            # Цитата контакта — вокруг САМОГО контакта, и берётся ближайшее к имени вхождение.
            syroe = (ch.get(pole) or '').strip()
            mesta = [m.start() for m in re.finditer(re.escape(syroe), tekst or '')]
            j = min(mesta, key=lambda p: abs(p - i)) if mesta and i >= 0 else (
                mesta[0] if mesta else -1)
            kon_v = citata(tekst, j, len(syroe)) if j >= 0 else kon
            nahodki.append((chto if rod == 'человек' else chto + ' (не нашей роли)',
                            v, imya, dolzh, kon_v))
    return nahodki


def main():
    parallel = dovod('--parallel', 3)
    stranic = dovod('--stranic', STRANIC)
    predel = dovod('--predel', 10 ** 9)
    vhod = dovod('--vhod', os.path.join(L, 'PARK-KONTAKTY-2S-SAJTY.csv'))
    vyhod = dovod('--vyhod', VYHOD)

    celi = []
    vidno = set()
    for r in chitat(vhod):
        i, s = (r.get('inn') or '').strip(), (r.get('sayt') or '').strip()
        if not i or not s or (i, s) in vidno:
            continue
        vidno.add((i, s))
        celi.append({'inn': i, 'sayt': s.rstrip('/'),
                     'predpriyatie': (r.get('predpriyatie') or '').strip()})
    proydeno = {(r['inn'], r['sayt']) for r in chitat(ZHURNAL)}
    celi = [c for c in celi if (c['inn'], c['sayt']) not in proydeno][:predel]
    if not celi:
        print('целей нет', file=sys.stderr)
        return
    print(f'сайтов: {len(celi)}, страниц на сайт: {stranic}', file=sys.stderr)

    js = sobrat_js(stranic)
    f, novyy, per, otl = hodok.dopisyvat(vyhod, COLS)
    w = csv.DictWriter(f, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy:
        w.writeheader()
    fz, novyy_z, _, _ = hodok.dopisyvat(ZHURNAL, COLS_ZH)
    wz = csv.DictWriter(fz, fieldnames=COLS_ZH, delimiter=';', extrasaction='ignore')
    if novyy_z:
        wz.writeheader()
    sch = {'сайтов': 0, 'страниц': 0, 'почт': 0, 'телефонов': 0, 'людей': 0,
           'не нашей роли': 0, 'сайт не открылся': 0, 'сбоев': 0}
    zamok = threading.Lock()

    def odna(c):
        return c, hodok.vzyat(c['sayt'] + '/', js, after_ms=2200, timeout=900)

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for n, (c, (r, kak, err)) in enumerate(pool.map(odna, celi), 1):
            with zamok:
                if r is None or kak == hodok.NE_OTKRYLSYA:
                    sch['сайт не открылся' if r is None else 'сбоев'] += 1
                    wz.writerow({'inn': c['inn'], 'sayt': c['sayt'], 'stranic_prosili': 0,
                                 'stranic_otvetili': 0, 'pocht': 0, 'telefonov': 0,
                                 'lyudey': 0, 'kak': kak,
                                 'pochemu': (err or 'не дошли')[:120]})
                    fz.flush()
                    continue
                sch['сайтов'] += 1
                stranicy = r.get('stranicy') or []
                otvetili = 0
                svoy = {'почта': 0, 'телефон': 0, 'человек': 0}
                bylo = set()
                for st in stranicy:
                    if not st.get('t'):
                        continue
                    otvetili += 1
                    sch['страниц'] += 1
                    for chto, znach, chel, dolzh, cit in razobrat(st['t'], st.get('mailto')):
                        if not st.get('u') or not cit:
                            continue      # ССЫЛКА И ЦИТАТА ОБЯЗАТЕЛЬНЫ: иначе строки нет
                        klyuch = (chto, znach, chel)
                        if klyuch in bylo:
                            continue
                        bylo.add(klyuch)
                        w.writerow({'inn': c['inn'], 'predpriyatie': c['predpriyatie'],
                                    'sayt': c['sayt'], 'chto_naydeno': chto,
                                    'znachenie': znach, 'chelovek': chel,
                                    'dolzhnost': dolzh, 'ssylka': st['u'], 'citata': cit})
                        # Счёт по ТОЧНОМУ виду находки: «человек не нашей роли» начинается
                        # со слова «человек», и счёт по первому слову записал бы врача в
                        # технические ЛПР — ровно то, что правка и чинит.
                        rod = ('не нашей роли' if 'не нашей роли' in chto
                               else chto.split()[0])
                        svoy[rod] = svoy.get(rod, 0) + 1
                f.flush()
                sch['почт'] += svoy.get('почта', 0)
                sch['телефонов'] += svoy.get('телефон', 0)
                sch['людей'] += svoy.get('человек', 0)
                sch['не нашей роли'] += svoy.get('не нашей роли', 0)
                wz.writerow({'inn': c['inn'], 'sayt': c['sayt'],
                             'stranic_prosili': len(stranicy),
                             'stranic_otvetili': otvetili, 'pocht': svoy.get('почта', 0),
                             'telefonov': svoy.get('телефон', 0),
                             'lyudey': svoy.get('человек', 0), 'kak': kak,
                             'pochemu': r.get('oshibka') or 'обойдено'})
                fz.flush()
                if n % 10 == 0 or n == len(celi):
                    print(f'  {n}/{len(celi)}: '
                          + ', '.join(f'{k} {v}' for k, v in sch.items()),
                          file=sys.stderr, flush=True)
    f.close()
    fz.close()
    print(f'готово: {sch}\n→ {vyhod}', file=sys.stderr)


if __name__ == '__main__':
    main()
