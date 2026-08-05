# -*- coding: utf-8 -*-
"""Сайт подтверждается ИНН НА ЕГО ЖЕ СТРАНИЦАХ — и это сразу первоисточник со ссылкой.

ОТКУДА ЗАДАЧА, числом. Поиск сайтов по 24 верхним покупателям P25 дал: подтверждено 10,
«чужой» 3, **«ничего» 11**. Но в «ничего» лежали `alrosa.ru`, `uacrussia.ru`,
`kurganpribor.ru`, `karmed.ru`, `kgs.kaluga.ru` — то есть сайты НАЙДЕНЫ и найдены верно, а
поле `verified` пустое. Судья не сказал «чужой», он сказал «не знаю», и следующее звено
прочитало это как «ничего нет». Шесть сайтов из первой двадцатки — 57 % денег — терялись на
пустом значении.

ПОЧЕМУ СУДЬЯ НЕ СМОГ. Он ищет ИНН на главной. У крупных компаний ИНН на главной не пишут:
он лежит в «Реквизитах», «Контактах», «Раскрытии информации» — то есть на одну ссылку глубже.
Это не свойство компании, а свойство глубины проверки.

ЧТО СЧИТАЕТСЯ ПОДТВЕРЖДЕНИЕМ. Только ИНН цифрами на странице сайта. Совпадение названия
подтверждением НЕ считается и пишется отдельным полем: «Апатит» есть и у АО «Апатит», и у
ОАО «Апатитстрой», и в новости о городе Апатиты. Название — повод посмотреть, ИНН — довод.

ХОЛДИНГ — ОТДЕЛЬНЫЙ ИСХОД, А НЕ «ЧУЖОЙ». `phosagro.ru` для АО «Апатит» и `knauf.ru` для
ООО «КНАУФ ГИПС БАЙКАЛ» судья пометил «чужой». Формально верно: юрлицо не то. Практически
это единственное место, где лежат структура и люди этого завода. Поэтому исход называется
`сайт группы`, и решение, брать оттуда людей или нет, принимается ПОСЛЕ, а не молчаливым
выбрасыванием.

Использование:
    python3 p25_sayt_podtverzhdenie.py --spisok <jsonl поиска> --parallel 4
    python3 p25_sayt_podtverzhdenie.py --inn 1433000147 --sajt alrosa.ru
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
VYHOD = os.path.join(L, 'P25-SAJTY.csv')
COLS = ['inn', 'predpriyatie', 'sayt', 'itog', 'chem_podtverzhden', 'ssylka', 'citata',
        'nazvanie_sovpalo', 'stranic_smotreli', 'kak']

# СЕРТИФИКАТЫ — ЧЕРЕЗ ОБЩИЙ ХОДОК `p25_hodok`, а не флагом на каждом запросе. Первый заход
# честный, `ignore_https_errors` подключается ТОЛЬКО вторым и только если до сайта не дошли;
# путь получения возвращается полем `kak` и уезжает в журнал. Так задумано по поправке 1-й
# сессии: включённый на всех подряд флаг выключает проверку подлинности там, где она работает.
# Заодно два захода разводят классы, которые я чуть не свалил в один: `alrosa.ru` и
# `uacrussia.ru` — сертификат НУЦ Минцифры (второй заход открывает), `kurganpribor.ru` — 503
# «сайт не добавлен на хостинг», там флаг ни при чём и адрес надо искать другой.

SKRIPT = r"""
window.__RES = (async () => {
  const INN = __INN__;
  const SLOVA = __SLOVA__;
  const SAJT = location.origin;
  const host = location.host;
  const pochinit = (u) => {
    try { const a = new URL(u, SAJT);
      if (a.protocol === 'http:' && a.host === host) a.protocol = 'https:';
      return a.href; } catch (e) { return null; }
  };
  const dostat = async (u) => {
    try { const r = await fetch(u, {redirect: 'follow'});
      return r.ok ? await r.text() : null; } catch (e) { return null; }
  };
  // ИНН ищется по ЦИФРАМ С ПРОБЕЛАМИ ТОЖЕ: в реквизитах его печатают и как «5103070023»,
  // и как «5103 070 023», и внутри строки «ИНН/КПП 5103070023/510301001».
  const cifry = INN.split('').join('[\\s\\u00a0]*');
  const re_inn = new RegExp(cifry);
  const tekst = (h) => (h || '').replace(/<script[\s\S]*?<\/script>/gi, ' ')
      .replace(/<style[\s\S]*?<\/style>/gi, ' ').replace(/<[^>]+>/g, ' ')
      .replace(/&nbsp;/gi, ' ').replace(/\s+/g, ' ');
  // ЧУЖОЙ ИНН НА САЙТЕ — ЭТО ОТВЕТ, А НЕ МОЛЧАНИЕ. Владелец показал карточку АО «Апатит»,
  // где сайтом стоит phosagro.ru: название на нём есть, наш ИНН — нет, и модуль отвечал
  // «название совпало». Но на сайте холдинга ЕСТЬ ИНН — только чужой, самого холдинга. Это
  // прямое доказательство, что домен принадлежит не нашему юрлицу, и оно сильнее совпадения
  // названия: названия дочек стоят на сайте группы всегда.
  const CHUZHOY = /ИНН[\s:\/№]*([57]\d{9}|\d{10})(?!\d)/g;
  const najti_chuzhoy = (h) => {
    const t = tekst(h);
    const est = [];
    let m;
    while ((m = CHUZHOY.exec(t)) !== null) {
      if (m[1] !== INN && !est.includes(m[1])) est.push(m[1]);
      if (est.length >= 3) break;
    }
    return est;
  };
  const najti = (h, u) => {
    const t = tekst(h);
    const m = t.match(re_inn);
    if (!m) return null;
    const i = Math.max(0, m.index - 90);
    return {ssylka: u, citata: t.slice(i, m.index + 60).trim()};
  };

  const out = {origin: SAJT, smotreli: [], nashli: null, slov_nazvaniya: 0,
               slov_vsego: SLOVA.length, chuzhie_inn: []};
  const glav = await dostat(SAJT + '/');
  if (glav === null) { out.oshibka = 'главная не открылась'; return JSON.stringify(out); }
  out.smotreli.push(SAJT + '/');
  out.nashli = najti(glav, SAJT + '/');
  // НАЗВАНИЕ СЛИЧАЕТСЯ С ТЕКСТОМ САЙТА, А НЕ С БУКВАМИ ДОМЕНА. Домен `smw.ru` и название
  // «СМЗ» совпали бы по двум буквам, а на странице настоящего владельца домена написано
  // «Ступинская металлургическая компания» — и несовпадение видно сразу.
  {
    const t = tekst(glav).toLowerCase();
    for (const s of SLOVA) if (t.includes(s)) out.slov_nazvaniya++;
  }

  // Страницы, где реквизиты живут на самом деле. Порядок — от самого вероятного.
  const NUZHNO = /rekvizit|contact|kontakt|raskryt|disclosure|about|o-kompanii|o-nas|invest|akcioner|shareholder|company/i;
  const kandidaty = [];
  for (const m of glav.matchAll(/<a[^>]+href=["']([^"'#]+)["']/gi)) {
    const a = pochinit(m[1]);
    if (!a || new URL(a).host !== host) continue;
    if (/\.(pdf|jpe?g|png|zip|docx?)$/i.test(a)) continue;
    if (NUZHNO.test(a) && !kandidaty.includes(a)) kandidaty.push(a);
  }
  // Стандартные пути добавляем В КОНЕЦ: они догадка, а ссылки с главной — факт о сайте.
  for (const p of ['/kontakty/', '/contacts/', '/rekvizity/', '/about/', '/o-kompanii/'])
    if (!kandidaty.includes(SAJT + p)) kandidaty.push(SAJT + p);

  for (const u of kandidaty.slice(0, 12)) {
    if (out.nashli) break;
    const h = await dostat(u);
    out.smotreli.push(u);
    if (h === null) continue;
    out.nashli = najti(h, u);
    if (!out.nashli && out.chuzhie_inn.length < 3) {
      for (const c of najti_chuzhoy(h)) {
        if (!out.chuzhie_inn.includes(c)) out.chuzhie_inn.push(c);
      }
    }
  }
  return JSON.stringify(out);
})();
"""


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


def normalizovat(s):
    s = (s or '').strip()
    if not s:
        return ''
    if not re.match(r'^https?://', s, re.I):
        s = 'https://' + s
    m = re.match(r'^(https?://[^/]+)', s, re.I)
    return m.group(1) if m else ''


def yadro_nazvaniya(n):
    """«ООО "КНАУФ ГИПС БАЙКАЛ"» → «кнауф гипс байкал». Форма собственности выбрасывается:
    она есть у всех и совпадением не является."""
    n = re.sub(r'[«»"\']', ' ', n or '')
    n = re.sub(r'\b(ООО|АО|ПАО|ОАО|ЗАО|АК|НПО|НПП|ФКП|ГУП|МУП|ФГУП|УК|ТД)\b', ' ', n, flags=re.I)
    return ' '.join(n.split()).lower()


def sprosit(sajt, inn, slova):
    """Через общий ходок: честный заход, флаг сертификата только вторым, `kak` — в провенанс."""
    js = (SKRIPT.replace('__INN__', json.dumps(inn))
          .replace('__SLOVA__', json.dumps(slova, ensure_ascii=False)))
    return hodok.vzyat(sajt + '/', js, after_ms=2500)


def celi_iz_jsonl(put, och):
    """Кандидаты берутся ИЗ ВСЕХ результатов поиска, включая отвергнутые и непроверенные:
    ровно там и лежали `alrosa.ru` и `uacrussia.ru`."""
    celi = []
    for l in open(put, encoding='utf-8'):
        try:
            x = json.loads(l)
        except json.JSONDecodeError:
            continue
        vidno = set()
        for y in (x.get('rezultaty') or []):
            s = normalizovat(y.get('site') or '')
            if not s or s in vidno:
                continue
            vidno.add(s)
            celi.append({'inn': x.get('inn') or '', 'sayt': s,
                         'predpriyatie': (och.get(x.get('inn'), {}).get('predpriyatie')
                                          or x.get('predpriyatie') or ''),
                         'sudya': str(y.get('verified'))})
    return celi


def main():
    parallel = dovod('--parallel', 3)
    predel = dovod('--predel', 10 ** 9)
    odin_inn = dovod('--inn', '')
    odin_sajt = dovod('--sajt', '')
    spisok = dovod('--spisok', '')

    och = {r['inn']: r for r in csv.DictReader(
        open(os.path.join(L, 'P25-OCHERED.csv'), encoding='utf-8-sig'), delimiter=';')}

    if odin_inn and odin_sajt:
        celi = [{'inn': odin_inn, 'sayt': normalizovat(odin_sajt),
                 'predpriyatie': och.get(odin_inn, {}).get('predpriyatie', ''), 'sudya': '-'}]
    else:
        celi = celi_iz_jsonl(spisok, och)
        gotovo = set()
        if os.path.exists(VYHOD):
            gotovo = {(r['inn'], r['sayt']) for r in csv.DictReader(
                open(VYHOD, encoding='utf-8-sig'), delimiter=';')}
        celi = [c for c in celi if (c['inn'], c['sayt']) not in gotovo]
        # ПОРЯДОК — ПО СУММЕ ПОКУПОК. Единственная сортировка задачи.
        celi.sort(key=lambda c: int(och.get(c['inn'], {}).get('mesto') or 10 ** 9))
        celi = celi[:predel]
    if not celi:
        print('целей нет', file=sys.stderr)
        return

    import predel_rannera
    predel_rannera.preduprezhdenie(parallel)
    print(f'проверок: {len(celi)}', file=sys.stderr)

    f, novyy, per, otl = hodok.dopisyvat(VYHOD, COLS)
    if per:
        print(f'  шапка обновлена, перенесено строк {per}', file=sys.stderr)
    if otl:
        print(f'  строки разной длины, {otl} отложено в *.rassoglasovan', file=sys.stderr)
    w = csv.DictWriter(f, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy:
        w.writeheader()
    sch = {'подтверждён ИНН': 0, 'название совпало': 0, 'не подтверждён': 0,
           'сайт не открылся': 0, 'сбоев': 0}
    lock = threading.Lock()

    def odna(c):
        return c, sprosit(c['sayt'], c['inn'],
                          [w for w in yadro_nazvaniya(c['predpriyatie']).split()
                           if len(w) > 3])

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for n, (c, (r, kak, err)) in enumerate(pool.map(odna, celi), 1):
            with lock:
                if r is None:
                    sch['сбоев'] += 1
                    print(f'  СБОЙ {c["sayt"]}: {err[:110]}', file=sys.stderr, flush=True)
                    continue
                nashli = r.get('nashli') or {}
                # Совпадением названия считается ВСЁ ядро целиком, а не одно слово из трёх:
                # «КНАУФ ГИПС ЧЕЛЯБИНСК» и «КНАУФ ГИПС БАЙКАЛ» делят два слова из трёх, и по
                # одному слову любой завод группы подошёл бы к любому другому.
                vsego = int(r.get('slov_vsego') or 0)
                sovpalo = bool(vsego) and int(r.get('slov_nazvaniya') or 0) == vsego
                # «САЙТ НЕ ОТКРЫЛСЯ» И «ИНН НЕ НАЙДЕН» — РАЗНЫЕ ФАКТЫ, и это ровно тот
                # класс ошибок, что весь день: у `kurganpribor.ru` домен отвечает «нет ни
                # одного сайта», страниц просмотрено НОЛЬ, а модуль писал «не подтверждён» —
                # то есть отчитывался о проверке, которой не было. Признак: браузер остался
                # на about:blank (`location.origin` строкой "null") либо не открылась главная.
                # «САЙТА НЕТ ВОВСЕ» ОТДЕЛЬНО ОТ «САЙТ НЕ ОТКРЫЛСЯ». В выдаче нашлись три
                # строки с `sayt = null`: у предприятия просто не было кандидата (одно из них
                # ИП — у него сайта и не бывает). Записывать это как «сайт не открылся»
                # значит сказать, что мы стучались и нам не ответили. Мы не стучались.
                if not (c.get('sayt') or '').strip() or c['sayt'] in ('null', 'https://null'):
                    itog, chem = 'кандидата сайта нет', 'поиск не дал ни одного домена'
                    sch['кандидата нет'] = sch.get('кандидата нет', 0) + 1
                elif kak == hodok.NE_OTKRYLSYA or (r.get('origin') or 'null') == 'null' \
                        or not (r.get('smotreli') or []):
                    itog, chem = 'сайт не открылся', (r.get('oshibka') or 'главная не открылась')
                    sch['сайт не открылся'] = sch.get('сайт не открылся', 0) + 1
                elif nashli:
                    itog, chem = 'подтверждён', 'ИНН на странице сайта'
                    sch['подтверждён ИНН'] += 1
                elif sovpalo and (r.get('chuzhie_inn') or []):
                    chuzh = ', '.join((r.get('chuzhie_inn') or [])[:2])
                    itog = 'сайт группы'
                    chem = (f'название совпало, но в реквизитах сайта ЧУЖОЙ ИНН ({chuzh}) — '
                            'это домен группы, а не этого юрлица')
                    sch['сайт группы'] = sch.get('сайт группы', 0) + 1
                elif sovpalo:
                    itog, chem = 'название совпало', 'только название, ИНН не найден'
                    sch['название совпало'] += 1
                else:
                    itog, chem = 'не подтверждён', 'ни ИНН, ни названия'
                    sch['не подтверждён'] += 1
                w.writerow({'inn': c['inn'], 'predpriyatie': c['predpriyatie'],
                            'sayt': r.get('origin') or c['sayt'], 'itog': itog,
                            'chem_podtverzhden': chem, 'ssylka': nashli.get('ssylka', ''),
                            'citata': (nashli.get('citata') or '')[:200],
                            'nazvanie_sovpalo': (f"{r.get('slov_nazvaniya')} из "
                                                 f"{r.get('slov_vsego')}"),
                            'stranic_smotreli': len(r.get('smotreli') or []),
                            'kak': kak})
                f.flush()
                if n % 5 == 0 or n == len(celi):
                    print(f'  {n}/{len(celi)}: ' + ', '.join(f'{k} {v}' for k, v in sch.items()),
                          file=sys.stderr, flush=True)
    f.close()
    print(f'готово: {sch}\n→ {VYHOD}', file=sys.stderr)


if __name__ == '__main__':
    main()
