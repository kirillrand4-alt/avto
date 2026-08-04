# -*- coding: utf-8 -*-
"""Страницы сайта предприятия ищутся ПО КАРТЕ, а не угадыванием путей. Метод №1 из шести.

ЗАЧЕМ. Во всём репозитории не было ни одного упоминания `robots.txt` и ни одного `sitemap` —
проверено поиском по всем модулям. Разбор структурных подразделений ходит «только по заданным
путям», и это его собственные слова. Угаданный путь отвечает 404 одинаково и когда страницы
нет, и когда она есть по другому адресу: `/contacts/` против `/kontakty/` против
`/o-kompanii/struktura/`. Первое — факт о сайте, второе — факт о нашем списке путей, и
отличить их без карты нельзя.

ПОРЯДОК, ровно как в ТЗ:
    robots.txt → строка `Sitemap:` → карта (в т.ч. `.gz`) → sitemap_index → меню главной →
    перебор путей
Перебор последний не из брезгливости: он единственный, кто не умеет сказать «страницы нет».

ПОЧЕМУ МЕНЮ ГЛАВНОЙ — НЕ ЗАПАСНОЙ ВАРИАНТ, А РАВНОПРАВНЫЙ. У заводов на «Битриксе» карта
часто содержит только товарный каталог: её генерирует модуль магазина, а страницы «Контакты»
и «Структура» лежат вне каталога и в карту не попадают. Там меню знает больше карты. Поэтому
меню спрашивается ВСЕГДА, а не только когда карта пуста, и источник каждой найденной страницы
записывается колонкой — иначе не понять, какой из способов работает.

ЗАПРОСЫ ИДУТ ИЗ САМОГО САЙТА. `fetch` выполняется на его же странице, то есть same-origin:
не нужен CORS, куки и заслон от ботов ведут себя как для обычного посетителя. Раннер живёт на
сервере владельца с настоящим браузером — это и есть причина не ходить curl-ом.

ЧЕГО МОДУЛЬ НЕ ДЕЛАЕТ. Не разбирает найденные страницы: его ответ — список адресов и откуда
каждый взят. Разбор — следующий модуль (метод №2, от ФИО). Смешивать их нельзя: тогда «людей
не нашли» перестанет отличаться от «страниц не нашли».

Использование:
    python3 p25_karta_sayta.py --sajt kaustik.ru
    python3 p25_karta_sayta.py --spisok engineers-lens/P25-SAJTY.csv --parallel 4
"""
import csv
import json
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import p25_hodok as hodok

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
KLIENT = os.path.join(BAZA, 'server', 'run_on_server.py')
VYHOD = os.path.join(L, 'P25-STRANICY-SAJTOV.csv')
KARTA = os.path.join(L, 'P25-karta-sajtov-zhurnal.csv')
COLS = ['inn', 'predpriyatie', 'sayt', 'stranica', 'otkuda', 'zagolovok', 'kak']
ZHCOLS = ['inn', 'sayt', 'origin', 'kak', 'robots', 'kart_najdeno', 'adresov_v_kartah', 'menyu_ssylok',
          'podoshlo', 'yazykovyh_kopiy', 'vzyato', 'otkuda_vzyato', 'pochemu']

# Потолок страниц на предприятие. Всё, что сверх, ПЕЧАТАЕТСЯ числом в журнал («подошло N,
# взято M»): молча срезанный хвост читается как «больше там ничего не было».
POTOLOK = 40

# ВЕС АДРЕСА. Потолок без веса — это отрезание СЛУЧАЙНЫХ страниц. На первом же прогоне
# Каустика подошёл 41 адрес при потолке 40, и выжила ли нужная страница, решил порядок меню:
# подраздел «О компании» дал 14 адресов вида «Награды», «Совет ветеранов», «Благотворительная
# помощь» — они прошли фильтр по слову `about`, и любой из них мог вытеснить
# `contacts/strukturnye-podrazdeleniya/`, ради которой всё и строилось.
VES = [
    (re.compile(r'struktur|podrazdelen', re.I), 0),      # прямо список людей отделами
    (re.compile(r'rukovod|management|apparat[-_]?upravlen|pravlenie', re.I), 1),
    (re.compile(r'sotrudnik|personal|komanda|team|nashi-lyudi', re.I), 2),
    (re.compile(r'kontakt|contact', re.I), 3),
    (re.compile(r'otdel|sluzhb|upravlen|administrac', re.I), 4),
    (re.compile(r'news|novosti|press', re.I), 5),        # назначения на должность, метод №4
    (re.compile(r'about|o-kompanii|o-predpriyatii|o-zavode', re.I), 6),
]


def ves_adresa(a, tekst):
    for r, v in VES:
        if r.search(a) or r.search(tekst or ''):
            return v
    return 9

# Фильтр адреса из ТЗ. Он намеренно широкий: цена лишнего адреса — один запрос, цена
# пропущенного — предприятие, закрытое как «людей нет».
NUZHNO = re.compile(
    r'contact|kontakt|struktur|podrazdelen|rukovod|management|team|about|upravlen|'
    r'otdel|sluzhb|personal|sotrudnik|komanda|apparat[-_]?upravlen|administrac|nashi-lyudi|'
    r'o-kompanii|o-predpriyatii|o-zavode|press|news|novosti|pressa', re.I)

# ЯЗЫКОВЫЕ КОПИИ. Карта Каустика отдала `/en/contacts/strukturnye-podrazdeleniya/` рядом с
# русским оригиналом — то же самое содержимое, второй запрос впустую, а при потолке в 40 ещё
# и вытесняющий русские страницы. Отсекаются ТОЛЬКО когда это префикс пути: `/en/...`, а не
# слово `en` где-то внутри адреса.
YAZYKI = re.compile(r'^https?://[^/]+/(?:en|eng|de|fr|es|cn|zh|it|tr)(?:/|$)', re.I)

# Адреса, которые под фильтр проходят, но людей не содержат никогда. Проверено глазами:
# `/news/` нужен (назначения на должность — метод №4), а `/news/rss` и постраничная
# навигация — это тот же список в тысяче копий.
MUSOR = re.compile(r'\.(?:jpg|jpeg|png|gif|svg|pdf|docx?|xlsx?|zip|rar)$|/rss|\?PAGEN|'
                   r'/page/\d|/tags?/|/search|/bitrix/|/upload/', re.I)

# СЕРТИФИКАТЫ — ЧЕРЕЗ ОБЩИЙ ХОДОК `p25_hodok`, а не флагом на каждом запросе. Первый заход
# честный, `ignore_https_errors` подключается ТОЛЬКО вторым и только если до сайта не дошли;
# путь получения возвращается полем `kak` и уезжает в журнал. Так задумано по поправке 1-й
# сессии: включённый на всех подряд флаг выключает проверку подлинности там, где она работает.
# Заодно два захода разводят классы, которые я чуть не свалил в один: `alrosa.ru` и
# `uacrussia.ru` — сертификат НУЦ Минцифры (второй заход открывает), `kurganpribor.ru` — 503
# «сайт не добавлен на хостинг», там флаг ни при чём и адрес надо искать другой.

SKRIPT = r"""
window.__RES = (async () => {
  // ORIGIN БЕРЁТСЯ СО СТРАНИЦЫ, А НЕ ИЗ НАШЕЙ СТРОКИ. Первый прогон на Каустике дал «robots
  // нет» и «адресов в картах 0», и это были показания сломанного прибора: мы открывали
  // `kaustik.ru`, сайт уводил на `www.kaustik.ru`, а запросы уходили по НАШЕМУ адресу — то
  // есть на другой origin. Браузер резал их как cross-origin, `fetch` кидал TypeError, и
  // модуль записывал «сайт ничего не отдал». Проверено запросом: `www.kaustik.ru/sitemap.xml`
  // отвечает 200 и это полноценный sitemapindex.
  const SAJT = location.origin;
  const PROSILI = __SAJT__;
  // СХЕМА ПОДТЯГИВАЕТСЯ ДО https ДЛЯ СВОЕГО ЖЕ ХОСТА. Третий случай одного класса за один
  // прогон: карта Каустика перечисляет вложенные карты по `http://www.kaustik.ru/...`, а
  // страница открыта по `https://`. Браузер режет такой запрос как mixed content, `fetch`
  // кидает TypeError, и модуль записывает «карта пуста». Сайт при этом отдаёт всё и по https.
  // Чужие хосты не трогаем: там подмена схемы была бы уже догадкой, а не исправлением.
  const svoy_host = location.host;
  const pochinit = (u) => {
    try {
      const a = new URL(u, location.origin);
      if (a.protocol === 'http:' && a.host === svoy_host) a.protocol = 'https:';
      return a.href;
    } catch (e) { return u; }
  };
  const dostat = async (u0) => {
    const u = pochinit(u0);
    try {
      const r = await fetch(u, {redirect: 'follow'});
      if (!r.ok) return null;
      // .gz распаковывается прямо в браузере: DecompressionStream есть в Chromium с 80-й
      // версии. Без него карты .gz читались бы как двоичный мусор и молча давали ноль адресов.
      if (/\.gz($|\?)/i.test(u)) {
        const ds = new DecompressionStream('gzip');
        const s = r.body.pipeThrough(ds);
        return await new Response(s).text();
      }
      return await r.text();
    } catch (e) { return null; }
  };
  const adresa = (xml) => [...(xml || '').matchAll(/<loc>\s*([^<\s]+)\s*<\/loc>/gi)].map(m => m[1]);
  const itog = {robots: '', karty: [], iz_kart: [], menyu: [], oshibki: [],
              origin: SAJT, prosili: PROSILI};

  // 1. robots.txt — единственное место, где сайт САМ называет адрес своей карты.
  const rob = await dostat(SAJT + '/robots.txt');
  if (rob !== null) {
    itog.robots = 'есть';
    for (const m of rob.matchAll(/^\s*Sitemap:\s*(\S+)/gim)) itog.karty.push(m[1]);
  } else { itog.robots = 'нет'; }

  // 2. Если не назвал — обычные имена. Это ещё не «перебор путей»: имена карт стандартизованы
  //    протоколом sitemaps.org, в отличие от адресов страниц.
  if (!itog.karty.length) {
    for (const im of ['/sitemap.xml', '/sitemap_index.xml', '/sitemap.xml.gz', '/sitemap/']) {
      const t = await dostat(SAJT + im);
      if (t && /<(?:urlset|sitemapindex)/i.test(t)) { itog.karty.push(SAJT + im); break; }
    }
  }

  // 3. Карты и вложенные карты. Глубина 2: sitemapindex → sitemap → адреса. Третий уровень
  //    в живой природе не встречается, а цикл по кругу — встречается.
  const vidno = new Set();
  const ochered = itog.karty.slice(0, 20);
  let glubina = 0;
  while (ochered.length && glubina < 60) {
    const u = ochered.shift(); glubina++;
    if (vidno.has(u)) continue; vidno.add(u);
    const t = await dostat(u);
    if (t === null) { itog.oshibki.push(u); continue; }
    const spisok = adresa(t);
    if (/<sitemapindex/i.test(t)) {
      for (const s of spisok.slice(0, 30)) {
        const p = pochinit(s);
        if (!vidno.has(p)) ochered.push(p);
      }
    } else {
      for (const s of spisok) itog.iz_kart.push(pochinit(s));
    }
    if (itog.iz_kart.length > 60000) break;
  }

  // 4. Меню главной — спрашивается ВСЕГДА. См. про «Битрикс» в шапке модуля.
  const glav = await dostat(SAJT + '/');
  if (glav !== null) {
    for (const m of glav.matchAll(/<a[^>]+href=["']([^"'#]+)["'][^>]*>([\s\S]{0,120}?)<\/a>/gi)) {
      let a = m[1];
      if (/^(?:mailto|tel|javascript):/i.test(a)) continue;
      if (a.startsWith('//')) a = 'https:' + a;
      else if (a.startsWith('/')) a = SAJT + a;
      else if (!/^https?:/i.test(a)) a = SAJT + '/' + a;
      itog.menyu.push([a, m[2].replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 80)]);
    }
  } else { itog.oshibki.push('главная не открылась'); }
  return JSON.stringify(itog);
})();
"""


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


def chitat(put):
    return list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(put) else []


def normalizovat(s):
    """`https://www.kaustik.ru/ru/` → `https://www.kaustik.ru`. Дальше всё клеится к корню."""
    s = (s or '').strip()
    if not s:
        return ''
    if not re.match(r'^https?://', s, re.I):
        s = 'https://' + s
    m = re.match(r'^(https?://[^/]+)', s, re.I)
    return m.group(1) if m else ''


def sprosit(sajt):
    """Ходок общий на все модули P25 (`p25_hodok`): первый заход честный, флаг сертификата —
    только вторым, и путь получения возвращается третьим значением для журнала."""
    js = SKRIPT.replace('__SAJT__', json.dumps(sajt))
    return hodok.vzyat(sajt + '/', js, after_ms=2500)


def otobrat(r, sajt):
    """Из сырого ответа — страницы, которые стоит открывать, с источником каждой.

    Меню идёт ПЕРВЫМ при равенстве: у ссылки из меню есть текст («Структура предприятия»),
    и он потом отвечает на вопрос «почему мы решили, что там люди». У адреса из карты текста
    нет вовсе."""
    svoy = re.escape(sajt.split('//', 1)[-1].split('/')[0].replace('www.', ''))
    nash = re.compile(r'https?://(?:www\.)?' + svoy, re.I)
    vyb, vidno, yazykovyh = [], set(), 0
    for a, tekst in (r.get('menyu') or []):
        if a in vidno or not nash.match(a) or MUSOR.search(a):
            continue
        if YAZYKI.match(a):
            yazykovyh += 1
            continue
        if NUZHNO.search(a) or NUZHNO.search(tekst):
            vidno.add(a)
            vyb.append((a, 'меню', tekst))
    iz_kart = r.get('iz_kart') or []
    for a in iz_kart:
        if a in vidno or not nash.match(a) or MUSOR.search(a):
            continue
        if YAZYKI.match(a):
            yazykovyh += 1
            continue
        if NUZHNO.search(a):
            vidno.add(a)
            vyb.append((a, 'карта', ''))
    # Сортировка устойчивая: при равном весе меню остаётся впереди карты, потому что у ссылки
    # меню есть текст, а он потом отвечает на вопрос «почему решили, что там люди».
    vyb.sort(key=lambda x: ves_adresa(x[0], x[2]))
    return vyb, len(iz_kart), yazykovyh


# ЗАСЛОН «ЭТО ВООБЩЕ НАШЕ ПРЕДПРИЯТИЕ». Первый прогон положил в данные P25 37 человек с
# `kaustik.ru` — а Каустика среди 491 покупателя НЕТ, я взял его тестовым сайтом при отладке.
# Данные были настоящие и хорошие, и именно поэтому опасные: отличить их от нужных потом
# нечем, ИНН у них пустой. Строка без ИНН из очереди P25 дальше не идёт.
def nash(inn, ochered):
    return bool((inn or '').strip()) and (inn or '').strip() in ochered


def main():
    parallel = dovod('--parallel', 3)
    predel = dovod('--predel', 10 ** 9)
    odin = dovod('--sajt', '')
    spisok = dovod('--spisok', os.path.join(L, 'P25-SAJTY.csv'))

    ochered = {r['inn'] for r in chitat(os.path.join(L, 'P25-OCHERED.csv'))}
    if odin:
        # Одиночный режим — отладочный. Он и положил в данные P25 37 человек с чужого сайта,
        # поэтому теперь пишет в ОТДЕЛЬНЫЙ файл, а не в общий.
        celi = [{'inn': '', 'predpriyatie': 'ОТЛАДКА', 'sayt': normalizovat(odin)}]
    else:
        celi = [{'inn': r.get('inn') or '', 'predpriyatie': r.get('predpriyatie') or '',
                 'sayt': normalizovat(r.get('sayt') or '')}
                for r in chitat(spisok) if normalizovat(r.get('sayt') or '')]
        proydeno = {r['inn'] for r in chitat(KARTA)}
        ne_nashi = sum(1 for c in celi if not nash(c['inn'], ochered))
        celi = [c for c in celi if nash(c['inn'], ochered) and c['inn'] not in proydeno][:predel]
        if ne_nashi:
            print(f'не из очереди P25 отброшено: {ne_nashi}', file=sys.stderr)
    if not celi:
        print('целей нет', file=sys.stderr)
        return

    import predel_rannera
    predel_rannera.preduprezhdenie(parallel)
    print(f'сайтов к обходу: {len(celi)}', file=sys.stderr)

    # Шапка сверяется ДО первой строки: колонку добавляют раз в жизни, а молча разъехавшийся
    # файл потом читается неверно всеми, кто к нему придёт.
    fv, novyy_v, per_v, otl_v = hodok.dopisyvat(VYHOD, COLS)
    fk, novyy_k, per_k, otl_k = hodok.dopisyvat(KARTA, ZHCOLS)
    for imya, per, otl in (('страницы', per_v, otl_v), ('журнал', per_k, otl_k)):
        if per:
            print(f'  {imya}: шапка обновлена, перенесено строк {per}', file=sys.stderr)
        if otl:
            print(f'  {imya}: строки разной длины, {otl} отложено в *.rassoglasovan',
                  file=sys.stderr)
    wv = csv.DictWriter(fv, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy_v:
        wv.writeheader()
    wk = csv.DictWriter(fk, fieldnames=ZHCOLS, delimiter=';', extrasaction='ignore')
    if novyy_k:
        wk.writeheader()

    sch = {'сайтов': 0, 'страниц': 0, 'из карты': 0, 'из меню': 0,
           'карта есть': 0, 'robots есть': 0, 'пусто': 0, 'сбоев': 0}
    lock = threading.Lock()

    def odna(c):
        return c, sprosit(c['sayt'])

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for n, (c, (r, kak, err)) in enumerate(pool.map(odna, celi), 1):
            with lock:
                if r is None or kak == hodok.NE_OTKRYLSYA:
                    sch['сбоев'] += 1
                    # Сбой В ЖУРНАЛ НЕ ПИШЕТСЯ: иначе предприятие навсегда останется
                    # «пройденным без страниц» — ложный ноль, закреплённый повторным прогоном.
                    print(f'  СБОЙ {c["sayt"]}: {err[:110]}', file=sys.stderr, flush=True)
                    continue
                sch['сайтов'] += 1
                if r.get('robots') == 'есть':
                    sch['robots есть'] += 1
                if r.get('karty'):
                    sch['карта есть'] += 1
                vyb, vsego_v_kartah, yazykovyh = otobrat(r, r.get('origin') or c['sayt'])
                vzyato = vyb[:POTOLOK]
                for a, otkuda, tekst in vzyato:
                    wv.writerow({'inn': c['inn'], 'predpriyatie': c['predpriyatie'],
                                 'sayt': c['sayt'], 'stranica': a, 'otkuda': otkuda,
                                 'zagolovok': tekst, 'kak': kak})
                    sch['страниц'] += 1
                    sch['из меню' if otkuda == 'меню' else 'из карты'] += 1
                if not vzyato:
                    sch['пусто'] += 1
                wk.writerow({'inn': c['inn'], 'sayt': c['sayt'],
                             'origin': r.get('origin') or '', 'kak': kak,
                             'robots': r.get('robots'),
                             'kart_najdeno': len(r.get('karty') or []),
                             'adresov_v_kartah': vsego_v_kartah,
                             'menyu_ssylok': len(r.get('menyu') or []),
                             'podoshlo': len(vyb), 'yazykovyh_kopiy': yazykovyh,
                             'vzyato': len(vzyato),
                             'otkuda_vzyato': ','.join(sorted({o for _, o, _ in vzyato})),
                             'pochemu': 'обойдено'})
                fv.flush()
                fk.flush()
                if n % 5 == 0 or n == len(celi):
                    print(f'  {n}/{len(celi)}: ' + ', '.join(f'{k} {v}' for k, v in sch.items()),
                          file=sys.stderr, flush=True)
    fv.close()
    fk.close()
    print(f'готово: {sch}\n→ {VYHOD}\n→ {KARTA}', file=sys.stderr)


if __name__ == '__main__':
    main()
