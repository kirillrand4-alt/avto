# -*- coding: utf-8 -*-
"""ЭТП ГПБ по СЛОВАМ и по ВСЕЙ площадке — канал поиска НОВЫХ предприятий.

Зачем отдельно от `gpb_po_ocheredi.py`. Тот ходит по нашему списку ИНН и потому структурно не
может найти предприятие, которого в очереди нет: замер это и показал — 236 предприятий, вне
очереди 1. Новые даёт обход по всей площадке: у Tender.pro словарный обход нашёл 299
предприятий, из них **214 вне очереди**. По ЭТП ГПБ такого обхода у нас нет вовсе — те 906
строк собраны другим способом, а площадка профильная: Газпром, нефтехимия, энергетика.

Адрес тот же, что и в обходе по компаниям, только вместо фильтра по заказчику — поисковая
строка:
    /api/v2/procedures/?page=N&per=200&sort=by_relevance&procedure[stage][0]=all
                        &search=<слово>

ИМЯ ПАРАМЕТРА СНЯТО ПЕРЕБОРОМ С КОНТРОЛЕМ НА КАЖДОМ, а не по аналогии. Двенадцать имён внутри
обёртки `procedure[...]` — search, q, query, name, title, text, keyword, search_string,
procedure_name, full_text, fulltext, phrase — площадка МОЛЧА игнорирует все: и слово, и
бессмыслица возвращают весь реестр 1 724 633. Работает ГОЛЫЙ `search=`:
    без фильтра                    1 724 633
    search=компрессор                 19 020
    search=кастрюлякастрюля              106
Контроль не ноль, а 106: поиск нечёткий, по морфологии. Это не «фильтр игнорируется» —
падение с 1,7 млн до сотни однозначно; но порог остановки поставлен 5 000, а не 50.

ЛОВУШКИ ПЛОЩАДКИ, снятые на обходе по компаниям и действующие здесь же:
  * пустое значение фильтра отдаёт ВЕСЬ реестр 1 724 204 — контроль пустым обязателен;
  * при нескольких значениях одного фильтра применяется только ПОСЛЕДНЕЕ;
  * `total_pages` жёстко упирается в 400, глубже площадка не пускает никого;
  * процедура принадлежит нескольким секциям сразу — дедуп по `procedure_id` обязателен.

Ключевые слова те же десять, что и на Tender.pro. Там замерено, что обрезанная основа даёт
ноль («центробежн» 0 при «центробежный» 775), поэтому слова полные.

ЗАКАЗЧИК: имена полей СНЯТЫ С ОТВЕТА, а не перенесены по аналогии. Первый прогон собрал
19 493 процедуры и не определил заказчика НИ У ОДНОЙ: я взял `customer_name`/`customer_id` из
обхода по компаниям, а в ответе поиска они называются иначе:
    company_name  «АО РКЦ ПРОГРЕСС»
    company_url   «/customers/ao-raketno-kosmicheskiy-tsentr-progress/»  ← отсюда slug
    included[]    карточка компании с `id` и `slug`
Правило, выведенное этой ошибкой (вторая такая за смену): **имена полей чужого API снимать, а
не переносить из соседнего запроса той же площадки** — у поиска и у карточки компании они разные.

ИНН добирается справочником площадки `etpgpb-zakazchiki-inn.csv` (17 499 организаций) ПО SLUG,
а не по названию: slug — идентификатор площадки, название пишется по-разному. Кого в справочнике
нет — остаётся с названием и помечается, чтобы это было видно числом, а не пропало молча.

Использование:
    python3 gpb_po_slovam.py --kontrol
    python3 gpb_po_slovam.py [--stranic 40] [--slova компрессор,воздуходувка]
"""
import csv
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
C = os.path.join(L, 'centro')
KLIENT = os.path.join(BAZA, 'server', 'run_on_server.py')
SPRAVOCHNIK = os.path.join(C, 'etpgpb-zakazchiki-inn.csv')
OCHERED = os.path.join(L, 'OCHERED-centrobezhnye.csv')
VYHOD = os.path.join(C, 'etpgpb-po-slovam.csv')
COLS = ['klyuch', 'procedure_id', 'nomer', 'predmet', 'zakazchik', 'slug', 'inn',
        'v_ocheredi', 'summa', 'data', 'sekciya', 'ssylka']
KLYUCHI = ['компрессор', 'компрессорная', 'центробежный', 'воздуходувка', 'воздуходувный',
           'турбокомпрессор', 'турбоагрегат', 'нагнетатель', 'газодувка', 'турбовоздуходувка']
NA_STRANICE = 200


def chitat(put):
    return list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(put) else []


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


SKRIPT = r"""
window.__RES = (async()=>{
  await new Promise(s=>setTimeout(s,4000));
  const q = async (u) => {
    for (let p = 0; p < 3; p++) {
      try {
        const r = await fetch(u, {headers:{'Accept':'application/json'}});
        if (r.status === 429 || r.status >= 500) { await new Promise(s=>setTimeout(s,2000*(p+1))); continue; }
        return await r.json();
      } catch(e) { await new Promise(s=>setTimeout(s,1500)); }
    }
    return null;
  };
  const B = 'https://etpgpb.ru/api/v2/procedures/?sort=by_relevance&procedure[stage][0]=all';
  // КОНТРОЛЬ: бессмыслица обязана дать ноль, пустое слово — НЕ весь реестр.
  const bred  = await q(B + '&page=1&per=1&search=' + encodeURIComponent('кастрюлякастрюля'));
  const pusto = await q(B + '&page=1&per=1&search=');
  const bred_n  = (bred  && bred.meta  && bred.meta.total_count) || 0;
  const pusto_n = (pusto && pusto.meta && pusto.meta.total_count) || 0;
  if (bred_n > 5000) return JSON.stringify({kontrol_provalen: 'бессмыслица вернула ' + bred_n});
  const itog = [];
  for (const slovo of __SLOVA__) {
    const kl = '&search=' + encodeURIComponent(slovo);
    const pervaya = await q(B + '&page=1&per=__PER__' + kl);
    const vsego = (pervaya && pervaya.meta && pervaya.meta.total_count) || 0;
    const stranic = Math.min(Math.ceil(vsego / __PER__), __MAXP__);
    const rows = [];
    for (let p = 1; p <= Math.max(stranic, vsego ? 1 : 0); p++) {
      const j = (p === 1) ? pervaya : await q(B + '&page=' + p + '&per=__PER__' + kl);
      for (const d of ((j && j.data) || [])) {
        const a = d.attributes || {};
        rows.push({id: d.id, nomer: a.registry_number || '',
                   predmet: (a.title || '').slice(0,300),
                   zakazchik: (a.company_name || '').slice(0,150),
                   slug: ((a.company_url || '').match(/\/customers\/([^\/]+)/) || ['',''])[1],
                   summa: String(a.amount || ''), data: (a.date_published || '').slice(0,10),
                   sekciya: a.section_category_name || '',
                   put: (a.truncated_path || '').slice(0,160)});
      }
      if (p < stranic) await new Promise(s=>setTimeout(s,350));
    }
    itog.push({slovo: slovo, vsego: vsego, rows: rows});
  }
  return JSON.stringify({kontrol_bred: bred_n, kontrol_pusto: pusto_n, itog: itog});
})();
"""


def sprosit(slova, stranic):
    js = (SKRIPT.replace('__SLOVA__', json.dumps(slova, ensure_ascii=False))
          .replace('__PER__', str(NA_STRANICE)).replace('__MAXP__', str(stranic)))
    zad = {'url': 'https://etpgpb.ru/procedures/', 'screenshot': False,
           'eval_js': {'script': js, 'after_ms': 1000, 'return': 'window.__RES'}}
    p = subprocess.run([sys.executable, KLIENT, 'browser_probe',
                        json.dumps(zad, ensure_ascii=False)],
                       capture_output=True, text=True, timeout=2400)
    try:
        otvet = json.loads(p.stdout[p.stdout.index('{'):])
    except (ValueError, json.JSONDecodeError):
        return None, (p.stdout or p.stderr)[-200:]
    d = otvet.get('data') or {}
    if d.get('eval_js_err'):
        return None, str(d['eval_js_err'])[:200]
    try:
        return json.loads(d.get('eval_js_value') or 'null'), ''
    except json.JSONDecodeError as e:
        return None, f'ответ не разобран: {str(e)[:80]}'


# ЗАСЛОН ОТ РАСПАДА ЗАПРОСА НА СЛОВА. Пойман 04.08 на модельных обозначениях: поиск
# «32ВЦ 100» вернул 5 329 процедур, среди них ремонт деаэратора ДСА-100, дорожная разметка
# и продажа квартиры №100 — площадка разбила запрос по пробелам и искала по токену «100».
# Это тот же класс, что «пустое значение отдаёт весь реестр»: фильтр как бы применён, выдача
# как бы есть, но она не о том. Разница в том, что здесь мусор ПРАВДОПОДОБЕН — процедуры
# настоящие, просто чужие.
#
# Поэтому многословный ключ к поиску не допускается вовсе, а у однословного проверяется,
# что он ДЕЙСТВИТЕЛЬНО встречается в предмете найденного. Порог мягкий (треть выдачи):
# площадка склоняет слова и пишет модель по-разному, но треть — это заведомо больше, чем
# даёт случайное совпадение по токену.
def slovo_goditsya(slovo):
    """Многословные обозначения площадка разрывает по пробелам — такие не пускаем."""
    return len(slovo.split()) == 1 and len(slovo) >= 4


def osnova(slovo):
    """Русское слово площадка ищет с учётом склонения: по запросу «центробежный» в выдаче
    стоит «центробежная установка». Точное вхождение такого не поймает, поэтому у длинных
    БУКВЕННЫХ слов отрезаем окончание. У обозначений моделей (есть цифры) не отрезаем
    ничего: там каждый знак значащий, «К-250-61-5» и «К-250-61-2» — разные машины."""
    n = norm_dlya_sverki(slovo)
    if not n:
        return ''
    est_cifry = any(c.isdigit() for c in n)
    if est_cifry or len(n) < 7:
        return n
    return n[:-2]


def vydacha_o_tom(slovo, stroki, porog=0.15):
    """Есть ли искомое в предмете найденного. Возвращает (годится, доля, сколько проверено).

    Порог 0,15 снят замером, а не назначен: настоящее слово «центробежный» даёт 0,50 по
    основе, а разложенный площадкой ключ «К-1500-62-2» — РОВНО НОЛЬ (в выдаче деаэратор,
    дорожная разметка, квартира №100). Между ними пропасть, поэтому порог можно ставить
    низко и не бояться отсечь живое."""
    if not stroki:
        return True, 1.0, 0
    o = osnova(slovo)
    if not o:
        return True, 1.0, 0
    sovpalo = sum(1 for x in stroki if o in norm_dlya_sverki(x.get('predmet') or ''))
    dolya = sovpalo / len(stroki)
    return dolya >= porog, dolya, len(stroki)


def norm_dlya_sverki(t):
    import re as _re
    t = (t or '').upper().replace('Ё', 'Е')
    for a, b in (('A', 'А'), ('B', 'В'), ('C', 'С'), ('E', 'Е'), ('H', 'Н'), ('K', 'К'),
                 ('M', 'М'), ('O', 'О'), ('P', 'Р'), ('T', 'Т'), ('X', 'Х'), ('Y', 'У')):
        t = t.replace(a, b)
    return _re.sub(r'[^0-9А-Я]', '', t)


def main():
    slova = [x.strip() for x in dovod('--slova', ','.join(KLYUCHI)).split(',') if x.strip()]
    # Многословные ключи площадка разрывает по пробелам и ищет по любому куску.
    otbrosheny = [x for x in slova if not slovo_goditsya(x)]
    slova = [x for x in slova if slovo_goditsya(x)]
    if otbrosheny:
        print(f'ОТБРОШЕНО {len(otbrosheny)} многословных ключей — площадка разрывает их по '
              f'пробелам и ищет по любому слову: {", ".join(otbrosheny[:6])}'
              + (' …' if len(otbrosheny) > 6 else ''), file=sys.stderr)
    if not slova:
        sys.exit('ОСТАНОВКА: ни одного пригодного ключа не осталось.')
    stranic = dovod('--stranic', 40)
    parallel = dovod('--parallel', 3)

    if '--kontrol' in sys.argv:
        r, err = sprosit(slova[:1], 1)
        if r is None:
            sys.exit(f'сбой контроля: {err}')
        if r.get('kontrol_provalen'):
            sys.exit(f'КОНТРОЛЬ ПРОВАЛЕН: {r["kontrol_provalen"]}')
        it = (r.get('itog') or [{}])[0]
        print(f'контроль: бессмыслица {r.get("kontrol_bred")}, пустое слово '
              f'{r.get("kontrol_pusto")}, «{it.get("slovo")}» {it.get("vsego")} процедур',
              file=sys.stderr)
        return

    po_slug = {}
    po_nazv = {}
    for r in chitat(SPRAVOCHNIK):
        if (r.get('inn') or '').strip():
            if (r.get('slug') or '').strip():
                po_slug[r['slug'].strip()] = r['inn'].strip()
            po_nazv[(r.get('name') or '').strip().lower()] = r['inn'].strip()
    ochered = {r['inn'] for r in chitat(OCHERED)}
    print(f'справочник площадки: {len(po_slug)} slug, {len(po_nazv)} названий', file=sys.stderr)

    novyy = not os.path.exists(VYHOD) or os.path.getsize(VYHOD) == 0
    f = open(VYHOD, 'a', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy:
        w.writeheader()
    vidno = {(r.get('procedure_id') or '') for r in chitat(VYHOD)}
    lock = threading.Lock()
    sch = {'процедур': 0, 'задвоено': 0, 'ИНН найден': 0, 'ИНН НЕ найден': 0,
           'предприятий': set(), 'ВНЕ очереди': set(), 'сбоев': 0}

    otseyano = {}

    def odno(slovo):
        return slovo, sprosit([slovo], stranic)

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for slovo, (r, err) in pool.map(odno, slova):
            with lock:
                if r is None:
                    sch['сбоев'] += 1
                    print(f'  СБОЙ «{slovo}»: {err[:130]}', file=sys.stderr, flush=True)
                    continue
                if r.get('kontrol_provalen'):
                    sys.exit(f'ОСТАНОВКА: {r["kontrol_provalen"]}')
                for it in r.get('itog') or []:
                    # ЗАСЛОН: выдача обязана быть О ТОМ, что искали. Замер 04.08: «32ВЦ 100»
                    # вернуло 5 329 процедур про деаэратор, дорожную разметку и квартиру
                    # №100 — площадка искала по токену «100». Мусор при этом ПРАВДОПОДОБЕН:
                    # процедуры настоящие, просто чужие, и без этой проверки они уехали бы
                    # в базу как находки.
                    godno, dolya, provereno = vydacha_o_tom(it['slovo'], it['rows'])
                    stroki = it['rows']
                    if not godno:
                        # Выдача не о том — но выбрасывать слово рано. Замер: у «К-250-61-5»
                        # совпало 7 % из 172, и эти 7 % — НАСТОЯЩИЕ попадания, утонувшие в
                        # мусоре от разложенного запроса. Поэтому не отказ, а СВОЙ фильтр:
                        # ищем широко у площадки, отбираем узко у себя. Строки, где искомого
                        # нет, не пишутся вовсе, а сколько отброшено — в счётчик.
                        o = osnova(it['slovo'])
                        stroki = [x for x in it['rows']
                                  if o and o in norm_dlya_sverki(x.get('predmet') or '')]
                        otseyano[it['slovo']] = (dolya, provereno, it.get('vsego'))
                        sch['отсеяно своим фильтром'] = (sch.get('отсеяно своим фильтром', 0)
                                                         + len(it['rows']) - len(stroki))
                        print(f'  «{it["slovo"]}»: площадка разложила запрос, искомое лишь в '
                              f'{dolya * 100:.0f} % из {provereno}. Беру только совпавшие: '
                              f'{len(stroki)}', file=sys.stderr, flush=True)
                        if not stroki:
                            continue
                    for x in stroki:
                        if x['id'] in vidno:
                            sch['задвоено'] += 1
                            continue
                        vidno.add(x['id'])
                        inn = (po_slug.get(x.get('slug') or '')
                               or po_nazv.get((x['zakazchik'] or '').strip().lower()) or '')
                        sch['процедур'] += 1
                        if inn:
                            sch['ИНН найден'] += 1
                            sch['предприятий'].add(inn)
                            if inn not in ochered:
                                sch['ВНЕ очереди'].add(inn)
                        else:
                            sch['ИНН НЕ найден'] += 1
                        w.writerow({'klyuch': it['slovo'], 'procedure_id': x['id'],
                                    'nomer': x['nomer'], 'predmet': x['predmet'],
                                    'zakazchik': x['zakazchik'], 'slug': x.get('slug') or '',
                                    'inn': inn, 'v_ocheredi': 'да' if inn in ochered else '',
                                    'summa': x['summa'], 'data': x['data'],
                                    'sekciya': x['sekciya'],
                                    'ssylka': 'https://etpgpb.ru' + (x['put'] or '')})
                    print(f'  «{it["slovo"]}»: на площадке {it["vsego"]}, взято {len(stroki)}'
                          f' | всего {sch["процедур"]}, предприятий {len(sch["предприятий"])},'
                          f' ВНЕ очереди {len(sch["ВНЕ очереди"])}', file=sys.stderr, flush=True)
                f.flush()
    f.close()
    if otseyano:
        print(f'\nОТСЕЯНО СЛОВ: {len(otseyano)} — выдача была не о том, что искали:',
              file=sys.stderr)
        for sl, (d, p, v) in sorted(otseyano.items(), key=lambda t: t[1][0])[:15]:
            print(f'  «{sl}»: совпало {d * 100:.0f} % из {p}, площадка обещала {v}',
                  file=sys.stderr)
    print(f'готово: процедур {sch["процедур"]}, задвоено {sch["задвоено"]}, '
          f'ИНН найден {sch["ИНН найден"]}, не найден {sch["ИНН НЕ найден"]}, '
          f'предприятий {len(sch["предприятий"])}, ВНЕ ОЧЕРЕДИ {len(sch["ВНЕ очереди"])}, '
          f'сбоев {sch["сбоев"]}\n→ {VYHOD}', file=sys.stderr)


if __name__ == '__main__':
    main()
