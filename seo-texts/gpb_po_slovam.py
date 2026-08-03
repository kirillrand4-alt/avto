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
                        &procedure[search]=<слово>

ЛОВУШКИ ПЛОЩАДКИ, снятые на обходе по компаниям и действующие здесь же:
  * пустое значение фильтра отдаёт ВЕСЬ реестр 1 724 204 — контроль пустым обязателен;
  * при нескольких значениях одного фильтра применяется только ПОСЛЕДНЕЕ;
  * `total_pages` жёстко упирается в 400, глубже площадка не пускает никого;
  * процедура принадлежит нескольким секциям сразу — дедуп по `procedure_id` обязателен.

Ключевые слова те же десять, что и на Tender.pro. Там замерено, что обрезанная основа даёт
ноль («центробежн» 0 при «центробежный» 775), поэтому слова полные.

ИНН заказчика в выдаче списка НЕ приходит — приходит название и `customer_id`. ИНН добирается
справочником площадки `etpgpb-zakazchiki-inn.csv` (17 499 организаций), а кого там нет —
остаётся с названием и помечается, чтобы это было видно числом, а не пропало молча.

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
COLS = ['klyuch', 'procedure_id', 'nomer', 'predmet', 'zakazchik', 'customer_id', 'inn',
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
  const bred  = await q(B + '&page=1&per=1&procedure[search]=' + encodeURIComponent('кастрюлякастрюля'));
  const pusto = await q(B + '&page=1&per=1&procedure[search]=');
  const bred_n  = (bred  && bred.meta  && bred.meta.total_count) || 0;
  const pusto_n = (pusto && pusto.meta && pusto.meta.total_count) || 0;
  if (bred_n > 50) return JSON.stringify({kontrol_provalen: 'бессмыслица вернула ' + bred_n});
  const itog = [];
  for (const slovo of __SLOVA__) {
    const kl = '&procedure[search]=' + encodeURIComponent(slovo);
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
                   zakazchik: (a.customer_name || a.customer || '').slice(0,150),
                   customer_id: String(a.customer_id || ''),
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


def main():
    slova = [x.strip() for x in dovod('--slova', ','.join(KLYUCHI)).split(',') if x.strip()]
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

    po_cid = {}
    po_nazv = {}
    for r in chitat(SPRAVOCHNIK):
        if (r.get('inn') or '').strip():
            po_cid[(r.get('company_id') or '').strip()] = r['inn'].strip()
            po_nazv[(r.get('name') or '').strip().lower()] = r['inn'].strip()
    ochered = {r['inn'] for r in chitat(OCHERED)}
    print(f'справочник площадки: {len(po_cid)} company_id, {len(po_nazv)} названий',
          file=sys.stderr)

    novyy = not os.path.exists(VYHOD) or os.path.getsize(VYHOD) == 0
    f = open(VYHOD, 'a', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy:
        w.writeheader()
    vidno = {(r.get('procedure_id') or '') for r in chitat(VYHOD)}
    lock = threading.Lock()
    sch = {'процедур': 0, 'задвоено': 0, 'ИНН найден': 0, 'ИНН НЕ найден': 0,
           'предприятий': set(), 'ВНЕ очереди': set(), 'сбоев': 0}

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
                    for x in it['rows']:
                        if x['id'] in vidno:
                            sch['задвоено'] += 1
                            continue
                        vidno.add(x['id'])
                        inn = (po_cid.get(x['customer_id'])
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
                                    'zakazchik': x['zakazchik'], 'customer_id': x['customer_id'],
                                    'inn': inn, 'v_ocheredi': 'да' if inn in ochered else '',
                                    'summa': x['summa'], 'data': x['data'],
                                    'sekciya': x['sekciya'],
                                    'ssylka': 'https://etpgpb.ru' + (x['put'] or '')})
                    print(f'  «{it["slovo"]}»: на площадке {it["vsego"]}, взято {len(it["rows"])}'
                          f' | всего {sch["процедур"]}, предприятий {len(sch["предприятий"])},'
                          f' ВНЕ очереди {len(sch["ВНЕ очереди"])}', file=sys.stderr, flush=True)
                f.flush()
    f.close()
    print(f'готово: процедур {sch["процедур"]}, задвоено {sch["задвоено"]}, '
          f'ИНН найден {sch["ИНН найден"]}, не найден {sch["ИНН НЕ найден"]}, '
          f'предприятий {len(sch["предприятий"])}, ВНЕ ОЧЕРЕДИ {len(sch["ВНЕ очереди"])}, '
          f'сбоев {sch["сбоев"]}\n→ {VYHOD}', file=sys.stderr)


if __name__ == '__main__':
    main()
