# -*- coding: utf-8 -*-
"""Закупки Сбербанк-АСТ по КАЖДОМУ предприятию очереди. Плюс справочник ИНН→КПП.

Пятая площадка. Две вводные, которые казались очевидными, оказались неверны, и без них
модуль бы не появился:

  1. «`purchaseList.aspx` отдаёт пустой `document.body`» — НЕТ. Пустое тело давал мёртвый
     прокси раннера. С `"proxy": ""` страница строится целиком (437 КБ, 78 скриптов).
     Это уже третий случай за сутки, когда живая площадка выглядела закрытой из-за прокси.
  2. «Фильтр организатора — скрытое поле `hiddenBuInnKppOrgDict`» — НЕТ. Оно лежит вне
     `#xmlContainer`, без `name` и без `content="leaf:"`, и МОЛЧА ни на что не влияет:
     запись в него значения не меняет собираемый XML вообще (2 699 → 2 699 байт).
     Ровно та ловушка, из-за которой мы дважды теряли прогоны на других площадках.

НАСТОЯЩИЙ ЗАПРОС (снят живым, авторизация не нужна):

    POST https://www.sberbank-ast.ru/SearchQuery.aspx?name=Main
    xmlData=<XML>&orgId=0&targetPageCode=ESPurchaseList&PID=0

XML берётся у самой страницы вызовом `getMainXmlFromPage()` — не собирается руками, поэтому
переименование любого поля площадкой нас не ломает молча. Подменяются только три узла:
    <orgDictionary><value>ИНН_КПП</value></orgDictionary>       ← организатор
    <CustomerDictionary><value>ИНН_КПП</value></CustomerDictionary>  ← заказчик
    <size>N</size><from>M</from>                                 ← листание

ФОРМАТ ЗНАЧЕНИЯ — `ИНН_КПП` через подчёркивание. Один ИНН без КПП даёт НОЛЬ, а не «все КПП»:
это не отсутствие закупок, а неверный ключ, и без контроля выглядело бы как «предприятия нет».
Несколько организаций разделяются `|;|`; запятая даёт ноль.

СПРАВОЧНИК ИНН→КПП (первый этап модуля) — побочная польза, которая нужна и Росэлторгу, и РТС:
    POST /SearchQuery.aspx?name=LongDictionary   data=<текст>&from=<int>
отдаёт `buInnKpp`, `buINN`, `buKPP`, `FullName`. У РТС программного резолвера ИНН→КПП нет
(его ajax требует antiforgery-токен и уводит на капчу), поэтому КПП для РТС берём отсюда.

КОНТРОЛИ, снятые числами до написания модуля (size=20, from=0):
    пустое значение             10 000 (relation gte)  ← фильтр снят, весь реестр
    7621008132_762101001            43 (eq)
    9999999999_999999999             0
    7621008132 (только ИНН)          0                 ← КПП обязателен
Пустое значение здесь отдаёт реестр целиком — как на ЭТП ГПБ и Tender.pro. Поэтому пустой
ключ = отказ до запроса, и контроль бессмыслицей повторяется на каждом прогоне.

ОТДЕЛЬНАЯ ЛОВУШКА: `orgCondition` (вкладка «искать по условию») — это НЕ фильтр по
организации, а нечёткий полнотекст: он вернул 10 000 записей и 12 разных организаций.
Для выгрузки по предприятию годится ТОЛЬКО `orgDictionary` / `CustomerDictionary`.

Elasticsearch режет `total` на 10 000 с `relation: gte` — для одного предприятия неважно,
но посчитать этим весь реестр нельзя.

Использование:
    python3 sberast_po_ocheredi.py --spravochnik      # только ИНН→КПП
    python3 sberast_po_ocheredi.py --kontrol
    python3 sberast_po_ocheredi.py --predel 20
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
OCHERED = os.path.join(L, 'OCHERED-centrobezhnye.csv')
EGRUL = os.path.join(C, 'ochered-egrul.csv')
SPRAVOCHNIK = os.path.join(C, 'sber-inn-kpp.csv')
VYHOD = os.path.join(C, 'sberast-po-kompaniyam.csv')
KARTA = os.path.join(C, 'sberast-obhod-zhurnal.csv')
COLS = ['inn', 'predpriyatie', 'rol', 'nomer', 'predmet', 'organizator', 'vid', 'summa',
        'data', 'data_zayavok', 'stadiya', 'istochnik', 'ssylka']
NA_STRANICE = 100        # проверено: size=100 отдаёт 100 записей одним запросом
STRANIC_MAX = 20         # 2 000 процедур на роль


def chitat(put):
    return list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(put) else []


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


# --------------------------------------------------------------- этап 1: справочник ИНН→КПП
SKRIPT_SPRAVOCHNIK = r"""
window.__RES = (async()=>{
  await new Promise(s=>setTimeout(s,5000));
  const spat = (ms) => new Promise(s=>setTimeout(s,ms));
  const sprosit = async (tekst) => {
    for (let t = 0; t < 3; t++) {
      try {
        const r = await fetch('https://www.sberbank-ast.ru/SearchQuery.aspx?name=LongDictionary', {
          method:'POST', credentials:'include',
          headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8',
                   'X-Requested-With':'XMLHttpRequest'},
          body:'data=' + encodeURIComponent(tekst) + '&from=0'});
        if (r.status === 429 || r.status >= 500) { await spat(2500*(t+1)); continue; }
        return await r.text();
      } catch(e) { await spat(1500); }
    }
    return '';
  };
  // Ответ — ДВОЙНОЙ JSON: {"result":"success","data":"<JSON эластика строкой>"}. Внутренние
  // кавычки экранированы, поэтому регулярка `"buInnKpp":"…"` не находит НИЧЕГО — и это молча
  // выглядит как «площадка не знает такой ИНН». Так и вышло 04.08: 640 предприятий подряд
  // получили ложную отметку «не знает», хотя площадка отвечала правильно.
  // Поэтому JSON разбирается двумя разборами и читается по пути, без регулярок.
  const razobrat = (t) => {
    let vnesh, vnutr;
    try { vnesh = JSON.parse(t); } catch(e) { return {pary: [], sboy: 'внешний JSON: ' + e}; }
    if (vnesh.result !== 'success') return {pary: [], sboy: 'result=' + vnesh.result};
    try { vnutr = JSON.parse(vnesh.data); } catch(e) { return {pary: [], sboy: 'внутренний JSON: ' + e}; }
    const hits = ((vnutr.hits || {}).hits) || [];
    const out = [], bylo = new Set();
    for (const h of hits) {
      const s = h._source || {};
      const k = s.buInnKpp || '';
      if (!k || bylo.has(k)) continue;
      bylo.add(k);
      out.push({inn: s.buINN || k.split('_')[0], kpp: s.buKPP || k.split('_')[1] || '',
                imya: s.FullName || ''});
    }
    return {pary: out, vsego: (((vnutr.hits || {}).total) || {}).value || 0, sboy: ''};
  };
  const ZADANIE = __ZADANIE__;
  const itog = [];
  for (const inn of ZADANIE) {
    const t = await sprosit(inn);
    const r = razobrat(t);
    itog.push({inn: inn, pary: r.pary, sboy: r.sboy || '', dlina: t.length});
    await spat(300);
  }
  return JSON.stringify({itog: itog});
})();
"""

# --------------------------------------------------------------------- этап 2: обход закупок
SKRIPT_OBHOD = r"""
window.__RES = (async()=>{
  await new Promise(s=>setTimeout(s,5000));
  const spat = (ms) => new Promise(s=>setTimeout(s,ms));
  let bazovyy = '';
  try { bazovyy = getMainXmlFromPage(); }
  catch(e) { return JSON.stringify({sboy: 'getMainXmlFromPage недоступен: ' + e}); }
  if (!bazovyy || bazovyy.length < 500)
    return JSON.stringify({sboy: 'базовый XML короче 500 знаков: ' + bazovyy.length});

  // Подмена узла с проверкой, что подмена вообще состоялась. Молчаливо не применившийся
  // фильтр — главная ловушка этой площадки, поэтому факт изменения строки проверяется.
  const postavit = (x, tag, val) => {
    const re = new RegExp('<' + tag + '><value>[^<]*</value></' + tag + '>');
    if (!re.test(x)) return null;
    return x.replace(re, '<' + tag + '><value>' + val + '</value></' + tag + '>');
  };
  const stranica = (x, size, from) =>
    x.replace(/<size>\d*<\/size>/, '<size>' + size + '</size>')
     .replace(/<from>\d*<\/from>/, '<from>' + from + '</from>');

  const zapros = async (xml) => {
    for (let t = 0; t < 3; t++) {
      try {
        const r = await fetch('https://www.sberbank-ast.ru/SearchQuery.aspx?name=Main', {
          method:'POST', credentials:'include',
          headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8',
                   'X-Requested-With':'XMLHttpRequest'},
          body:'xmlData=' + encodeURIComponent(xml) +
               '&orgId=0&targetPageCode=ESPurchaseList&PID=0'});
        if (r.status === 429 || r.status >= 500) { await spat(3000*(t+1)); continue; }
        const o = JSON.parse(await r.text());
        if (o.result !== 'success') { await spat(2000); continue; }
        return JSON.parse(o.data);
      } catch(e) { await spat(2000); }
    }
    return null;
  };

  const P = new DOMParser();
  const razobrat = (tableXml) => {
    const d = P.parseFromString(tableXml, 'text/xml');
    const tot = d.querySelector('total > value');
    const rel = d.querySelector('total > relation');
    const rows = [];
    for (const h of d.querySelectorAll('hits')) {
      const s = h.querySelector('_source');
      if (!s) continue;
      const p = (t) => { const e = s.querySelector(t); return e ? e.textContent : ''; };
      rows.push({n: p('purchCodeTerm'),
                 t: (p('purchName') || p('BidName')).slice(0,300),
                 o: p('OrgName'), v: p('PurchaseTypeName'), s: p('purchAmount'),
                 dp: p('PublicDate'), dz: p('RequestDate'), st: p('purchStateName'),
                 i: p('SourceTerm'), u: p('objectHrefTerm')});
    }
    return {vsego: tot ? tot.textContent : '', otnoshenie: rel ? rel.textContent : '',
            rows: rows};
  };

  // КОНТРОЛЬ на каждом прогоне: бессмыслица обязана вернуть 0, иначе сужение не применяется
  // и в панель уехал бы весь реестр площадки.
  const xb = postavit(bazovyy, 'orgDictionary', '9999999999_999999999');
  if (xb === null) return JSON.stringify({sboy: 'узел orgDictionary не найден в XML'});
  const rb = await zapros(stranica(xb, 5, 0));
  if (rb === null) return JSON.stringify({sboy: 'контрольный запрос не ответил'});
  const kb = razobrat(rb.tableXml || '');
  if (parseInt(kb.vsego || '0', 10) > 0)
    return JSON.stringify({kontrol_provalen: 'бессмыслица вернула ' + kb.vsego});

  const ZADANIE = __ZADANIE__;
  const TEGI = {'organizator': 'orgDictionary', 'zakazchik': 'CustomerDictionary'};
  const itog = [];
  for (const z of ZADANIE) {
    for (const rol of Object.keys(TEGI)) {
      let x = postavit(bazovyy, TEGI[rol], z.kluch);
      if (x === null) { itog.push({inn: z.inn, rol: rol, sboy: 'узел ' + TEGI[rol] + ' не найден'}); continue; }
      const pervaya = await zapros(stranica(x, __RAZMER__, 0));
      await spat(600);
      if (pervaya === null) { itog.push({inn: z.inn, rol: rol, sboy: 'нет ответа'}); continue; }
      const k = razobrat(pervaya.tableXml || '');
      const vsego = parseInt(k.vsego || '0', 10);
      const rows = k.rows;
      const nado = Math.min(Math.ceil(vsego / __RAZMER__), __MAXP__);
      for (let p = 1; p < nado; p++) {
        const dop = await zapros(stranica(x, __RAZMER__, p * __RAZMER__));
        await spat(600);
        if (dop === null) break;
        for (const r of razobrat(dop.tableXml || '').rows) rows.push(r);
      }
      const imena = Array.from(new Set(rows.map(r=>r.o).filter(Boolean)));
      itog.push({inn: z.inn, kluch: z.kluch, rol: rol, vsego: vsego,
                 otnoshenie: k.otnoshenie, vzyato_stranic: nado, imen: imena.length,
                 rows: rows});
    }
  }
  return JSON.stringify({itog: itog});
})();
"""


def sprosit(skript, zadanie, tayminaut, zameny=None):
    js = skript.replace('__ZADANIE__', json.dumps(zadanie, ensure_ascii=False))
    for k, v in (zameny or {}).items():
        js = js.replace(k, str(v))
    zad = {'url': 'https://www.sberbank-ast.ru/purchaseList.aspx', 'screenshot': False,
           'proxy': '', 'eval_js': {'script': js, 'after_ms': 10000, 'return': 'window.__RES'}}
    try:
        p = subprocess.run([sys.executable, KLIENT, 'browser_probe',
                            json.dumps(zad, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=tayminaut)
    except subprocess.TimeoutExpired:
        return None, f'раннер не ответил за {tayminaut} с'
    try:
        otvet = json.loads(p.stdout[p.stdout.index('{'):])
    except (ValueError, json.JSONDecodeError):
        return None, (p.stdout or p.stderr or 'пустой ответ раннера')[-200:]
    d = otvet.get('data') or {}
    if d.get('eval_js_err'):
        return None, str(d['eval_js_err'])[:200]
    znach = d.get('eval_js_value')
    if znach in (None, '', 'null'):
        return None, ('eval_js_value пуст. ключи: ' + ','.join(sorted(d.keys()))
                      + f" | http_status={d.get('http_status')}"
                      + f" | error={str(d.get('error'))[:120]}")
    try:
        return json.loads(znach), ''
    except json.JSONDecodeError as e:
        return None, f'ответ не разобран: {str(e)[:80]}'


def sobrat_spravochnik(inny, pachka, parallel):
    """ИНН → все пары ИНН_КПП, какие знает площадка. Дописывает, не переписывает."""
    est = {r['inn'] for r in chitat(SPRAVOCHNIK)}
    nado = [i for i in inny if i not in est]
    print(f'[справочник] спросить {len(nado)} ИНН (уже есть {len(est)})', file=sys.stderr)
    if not nado:
        return
    novyy = not os.path.exists(SPRAVOCHNIK) or os.path.getsize(SPRAVOCHNIK) == 0
    f = open(SPRAVOCHNIK, 'a', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=['inn', 'kpp', 'inn_kpp', 'imya'], delimiter=';',
                       extrasaction='ignore')
    if novyy:
        w.writeheader()
    pachki = [nado[i:i + pachka] for i in range(0, len(nado), pachka)]
    lock = threading.Lock()
    sch = {'спрошено': 0, 'с парами': 0, 'пар': 0, 'сбоев': 0}

    def odna(gr):
        return gr, sprosit(SKRIPT_SPRAVOCHNIK, gr, 300 + len(gr) * 12)

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for nomer, (gr, (r, err)) in enumerate(pool.map(odna, pachki), 1):
            with lock:
                if r is None:
                    sch['сбоев'] += len(gr)
                    print(f'  СБОЙ {nomer}: {err[:130]}', file=sys.stderr, flush=True)
                    continue
                for it in r.get('itog') or []:
                    if it.get('sboy'):
                        # Разбор не удался — это НЕ «площадка не знает ИНН». Ложная отметка
                        # кэшируется и навсегда закрывает предприятие от повторного спроса,
                        # поэтому такие строки не пишутся вовсе, ИНН останется в очереди.
                        sch['сбоев'] += 1
                        print(f'  разбор не удался {it["inn"]}: {str(it["sboy"])[:90]}',
                              file=sys.stderr, flush=True)
                        continue
                    sch['спрошено'] += 1
                    pary = it.get('pary') or []
                    if pary:
                        sch['с парами'] += 1
                    sch['пар'] += len(pary)
                    for p in pary:
                        w.writerow({'inn': it['inn'], 'kpp': p['kpp'],
                                    'inn_kpp': p['inn'] + '_' + p['kpp'],
                                    'imya': p.get('imya') or ''})
                    if not pary:
                        # пустая строка-отметка: ИНН спрошен, площадка его не знает
                        w.writerow({'inn': it['inn'], 'kpp': '', 'inn_kpp': '',
                                    'imya': 'площадка не знает этот ИНН'})
                f.flush()
                print(f'  [справочник] {min(nomer*pachka, len(nado))}/{len(nado)}: {sch}',
                      file=sys.stderr, flush=True)
    f.close()
    print(f'справочник готов: {sch}\n→ {SPRAVOCHNIK}', file=sys.stderr)


def main():
    predel = dovod('--predel', 10 ** 9)
    pachka = dovod('--pachka', 2)
    parallel = dovod('--parallel', 4)
    stranic = dovod('--stranic', STRANIC_MAX)
    razmer = dovod('--razmer', NA_STRANICE)
    tayminaut = 900 + pachka * stranic * 2 * 10

    och = chitat(OCHERED)
    if len(och) < 300:
        sys.exit(f'ОСТАНОВКА: очередь {len(och)} строк — пересоберите базу перед обходом.')
    imya_po_inn = {r['inn']: r.get('predpriyatie') or '' for r in och}

    if '--spravochnik' in sys.argv:
        sobrat_spravochnik([r['inn'] for r in och][:predel],
                           dovod('--pachka', 40), parallel)
        return

    # Ключи ИНН_КПП: сначала из справочника площадки, чего нет — из ЕГРЮЛ.
    kluchi = {}
    for r in chitat(SPRAVOCHNIK):
        if r.get('inn_kpp'):
            kluchi.setdefault(r['inn'], []).append(r['inn_kpp'])
    iz_egrul = 0
    for r in chitat(EGRUL):
        if r['inn'] in imya_po_inn and r['inn'] not in kluchi and (r.get('kpp') or '').strip():
            kluchi[r['inn']] = [r['inn'] + '_' + r['kpp'].strip()]
            iz_egrul += 1
    print(f'ключей ИНН_КПП: {len(kluchi)} предприятий '
          f'(из них {iz_egrul} по КПП из ЕГРЮЛ, справочник площадки их не знает)',
          file=sys.stderr)

    proydeno = {r['inn'] for r in chitat(KARTA)}
    celi = []
    for inn, spisok in kluchi.items():
        if inn in proydeno:
            continue
        for k in spisok:
            celi.append({'inn': inn, 'kluch': k})
    celi = celi[:predel]
    print(f'[Сбербанк-АСТ] к обходу {len(celi)} ключей (пройдено {len(proydeno)} ИНН)',
          file=sys.stderr)

    if '--kontrol' in sys.argv:
        # Контроль С ДВУХ КОНЦОВ. Одной бессмыслицы мало: она не ловит «площадка молча
        # отдаёт пусто всем», а это у нас было трижды. Рядом всегда стоит ключ, про который
        # заранее известно, что он непустой: 7621008132_762101001 → 43 записи (снято живым).
        r, err = sprosit(SKRIPT_OBHOD,
                         [{'inn': '7621008132', 'kluch': '7621008132_762101001'}] + celi[:1],
                         tayminaut, {'__RAZMER__': 20, '__MAXP__': 1})
        if r is None:
            sys.exit(f'сбой контроля: {err}')
        if r.get('sboy'):
            sys.exit(f'сбой: {r["sboy"]}')
        if r.get('kontrol_provalen'):
            sys.exit(f'КОНТРОЛЬ ПРОВАЛЕН: {r["kontrol_provalen"]}')
        po_rolyam = {}
        for it in r.get('itog') or []:
            print(f'  {it.get("inn")} {it.get("rol")}: vsego={it.get("vsego")} '
                  f'({it.get("otnoshenie")}), взято {len(it.get("rows") or [])}, '
                  f'организаторов {it.get("imen")}, сбой={it.get("sboy")}', file=sys.stderr)
            if it.get('inn') == '7621008132':
                po_rolyam[it.get('rol')] = it.get('vsego') or 0
        if not any(po_rolyam.values()):
            sys.exit('КОНТРОЛЬ ПРОВАЛЕН: заведомо непустой ключ 7621008132_762101001 дал '
                     'ноль по обеим ролям — площадка отдаёт пусто всем, собирать нечего.')
        print(f'контроль пройден: бессмыслица 0, известный ключ {po_rolyam}', file=sys.stderr)
        return
    if not celi:
        return

    novyy_v = not os.path.exists(VYHOD) or os.path.getsize(VYHOD) == 0
    novyy_k = not os.path.exists(KARTA) or os.path.getsize(KARTA) == 0
    fv = open(VYHOD, 'a', encoding='utf-8-sig', newline='')
    wv = csv.DictWriter(fv, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy_v:
        wv.writeheader()
    fk = open(KARTA, 'a', encoding='utf-8-sig', newline='')
    wk = csv.DictWriter(fk, fieldnames=['inn', 'kluch', 'rol', 'vsego', 'vzyato', 'pochemu'],
                        delimiter=';', extrasaction='ignore')
    if novyy_k:
        wk.writeheader()

    sch = {'ключей': 0, 'процедур': 0, 'пусто': 0, 'обрезано потолком': 0, 'сбоев': 0}
    pachki = [celi[i:i + pachka] for i in range(0, len(celi), pachka)]
    lock = threading.Lock()

    def odna(gr):
        return gr, sprosit(SKRIPT_OBHOD, gr, tayminaut,
                           {'__RAZMER__': razmer, '__MAXP__': stranic})

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for nomer, (gr, (r, err)) in enumerate(pool.map(odna, pachki), 1):
            with lock:
                if r is None or r.get('sboy'):
                    sch['сбоев'] += len(gr)
                    print(f'  СБОЙ пачки {nomer}: {(err or r.get("sboy"))[:150]}',
                          file=sys.stderr, flush=True)
                    continue
                if r.get('kontrol_provalen'):
                    sys.exit(f'ОСТАНОВКА: {r["kontrol_provalen"]}. Сужение не применяется.')
                for it in r.get('itog') or []:
                    if it.get('sboy'):
                        sch['сбоев'] += 1
                        continue
                    sch['ключей'] += 1
                    rows = it.get('rows') or []
                    sch['процедур'] += len(rows)
                    if not rows:
                        sch['пусто'] += 1
                    vsego = it.get('vsego') or 0
                    obrezano = vsego > len(rows)
                    if obrezano:
                        sch['обрезано потолком'] += 1
                    wk.writerow({'inn': it['inn'], 'kluch': it.get('kluch') or '',
                                 'rol': it.get('rol') or '', 'vsego': vsego,
                                 'vzyato': len(rows),
                                 'pochemu': (f'ВЗЯТО НЕ ВСЁ: всего {vsego} '
                                             f'({it.get("otnoshenie")}) — поднять --stranic'
                                             if obrezano else 'обойдено')})
                    for x in rows:
                        wv.writerow({'inn': it['inn'],
                                     'predpriyatie': imya_po_inn.get(it['inn']) or '',
                                     'rol': it.get('rol') or '', 'nomer': x.get('n') or '',
                                     'predmet': x.get('t') or '',
                                     'organizator': x.get('o') or '', 'vid': x.get('v') or '',
                                     'summa': x.get('s') or '', 'data': x.get('dp') or '',
                                     'data_zayavok': x.get('dz') or '',
                                     'stadiya': x.get('st') or '',
                                     'istochnik': x.get('i') or '',
                                     'ssylka': x.get('u') or ''})
                fv.flush()
                fk.flush()
                print(f'  [сбер] {min(nomer*pachka, len(celi))}/{len(celi)}: {sch}',
                      file=sys.stderr, flush=True)

    fv.close()
    fk.close()
    print(f'готово: {sch}\n→ {VYHOD}\n→ {KARTA}', file=sys.stderr)


if __name__ == '__main__':
    main()
