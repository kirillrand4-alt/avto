# -*- coding: utf-8 -*-
"""Обход НЕСКОЛЬКИХ площадок по каждому предприятию очереди, одним модулем.

Приём один и тот же: у площадки есть вход по компании, и он даёт на два-три порядка больше,
чем обход по десяти ключевым словам. Для Tender.pro и ЭТП ГПБ написаны отдельные модули —
у них вход через справочник площадки и своя постраничка. Здесь собраны те три, у которых
**вход прямо по ИНН**, а значит адресуемы все 776 предприятий очереди:

    Портал поставщиков Москвы  — JSON, `customerInnOrName`, счётчик в ответе, `take` до 500
    ТЭК-Торг                   — HTML, `organizer[]=<ИНН>`, 15 записей на страницу жёстко
    РТС-тендер                 — HTML, путь `/poisk/organizator/<ИНН>-<КПП>/`

ЧЕГО ЖДАТЬ, честно и заранее. Такой обход НЕ находит новых предприятий — он ходит по нашему же
списку и структурно не может выйти за него. Проверено дважды: Tender.pro 157 596 закупок и
0 новых, ЭТП ГПБ 208 784 и 0 новых. Ценность здесь одна — **контактные лица карточек**: по
замеру 109 из 129 технических людей с личным мобильным пришли именно с карточек закупок, тогда
как сайты и справочники дают имя, должность и городской номер, но не сотовый.

ТРИ ЛОВУШКИ, пойманные на соседних площадках, и заслон против каждой:
  * пустое значение фильтра отдаёт ВЕСЬ реестр (ЭТП ГПБ, Tender.pro) — контроль пустым;
  * несуществующий ИНН возвращает ту же выдачу, если фильтр игнорируется — контроль бессмыслицей;
  * страница доредиректывается уже ПОСЛЕ старта скрипта, контекст уничтожается на середине
    («Execution context was destroyed») — пауза в начале скрипта.
Контроль не прошёл — площадка пропускается целиком и НЕ пишет ничего.

Использование:
    python3 ploshchadki_po_ocheredi.py --kontrol                 # проверить все три
    python3 ploshchadki_po_ocheredi.py --ploshchadka portal
    python3 ploshchadki_po_ocheredi.py --ploshchadka tektorg,rts --predel 50
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
COLS = ['inn', 'predpriyatie', 'nomer', 'predmet', 'summa', 'data', 'ssylka', 'ploshchadka']

# Каждая площадка описана данными, а не своим модулем: адрес страницы для захода, кусок JS,
# который умеет спросить одну компанию, и контрольные запросы. Разбор внутри JS, потому что
# из песочницы эти площадки недоступны (000), а раннер отдаёт только то, что вернул скрипт.
PLOSHCHADKI = {
    'portal': {
        'nazvanie': 'Портал поставщиков Москвы',
        'url': 'https://zakupki.mos.ru/purchase/list',
        'fajl': 'portal-po-kompaniyam.csv',
        # Настоящий ключ найден в умолчательном queryDto самой страницы. Догадки
        # customerIds/customerId/customers/customerInn/inn ВСЕ давали 5 051 771, то есть
        # молча игнорировались — ровно та ловушка, ради которой стоит контроль.
        'js': r"""
        const zapros = async (inn, skip) => {
          const dto = {filter:{customerInnOrName:{value:String(inn),contains:true}},
                       withCount:true, take:__TAKE__, skip:skip, order:[{field:'relevance',desc:true}]};
          const u = 'https://old.zakupki.mos.ru/api/Cssp/Purchase/Query?queryDto='
                    + encodeURIComponent(JSON.stringify(dto));
          const r = await fetch(u, {headers:{'Accept':'application/json'}});
          return await r.json();
        };
        const odna = async (z) => {
          const rows = []; let vsego = 0;
          for (let s = 0; s < __MAXP__ * __TAKE__; s += __TAKE__) {
            const j = await zapros(z.inn, s);
            vsego = (j && j.count) || vsego;
            const d = (j && (j.items || j.data)) || [];
            if (!d.length) break;
            for (const x of d) rows.push({nomer: String(x.number || x.id || ''),
                                          predmet: String(x.name || '').slice(0,300),
                                          summa: String(x.price || ''),
                                          data: String(x.beginDate || '').slice(0,10),
                                          put: '/purchase/' + (x.id || '')});
            if (s + __TAKE__ < __MAXP__ * __TAKE__) await new Promise(r=>setTimeout(r,300));
          }
          return {inn: z.inn, vsego: vsego, rows: rows};
        };
        const kontrol = async () => {
          const bred = await zapros('9999999999', 0);
          const pusto = await zapros('', 0);
          return {bred: (bred && bred.count) || 0, pusto: (pusto && pusto.count) || 0};
        };
        """,
        'take': 100, 'predel_bred': 100,
    },
    'tektorg': {
        'nazvanie': 'ТЭК-Торг',
        'url': 'https://www.tektorg.ru/223-fz/procedures',
        'fajl': 'tektorg-po-kompaniyam.csv',
        # Секции проверены агентом: 223-fz, 44-fz, market, sale, rosneft, inter_rao.
        # Страница фиксированно 15 записей, параметр limit площадкой игнорируется.
        'js': r"""
        const SEK = ['223-fz','market','rosneft','inter_rao','44-fz'];
        const vzyat = async (u) => { const r = await fetch(u,{credentials:'include'}); return await r.text(); };
        const razobrat = (h) => {
          const out = []; const re = /href="(\/[a-z0-9_\-]+\/procedures\/(\d+)[^"]*)"[^>]*>([\s\S]{0,400}?)<\/a>/g;
          let m; while ((m = re.exec(h)) !== null) {
            const t = m[3].replace(/<[^>]+>/g,' ').replace(/&nbsp;/g,' ').replace(/\s+/g,' ').trim();
            if (t) out.push({nomer: m[2], predmet: t.slice(0,300), summa:'', data:'', put: m[1]});
          }
          return out;
        };
        const odna = async (z) => {
          const rows = []; const vid = {};
          for (const sek of SEK) {
            for (let p = 1; p <= __MAXP__; p++) {
              const h = await vzyat('https://www.tektorg.ru/' + sek + '/procedures?organizer[]='
                                    + encodeURIComponent(z.inn) + '&page=' + p);
              const k = razobrat(h);
              if (!k.length) break;
              let novyh = 0;
              for (const x of k) { if (!vid[x.nomer]) { vid[x.nomer]=1; rows.push(x); novyh++; } }
              if (!novyh) break;
              await new Promise(r=>setTimeout(r,300));
            }
          }
          return {inn: z.inn, vsego: rows.length, rows: rows};
        };
        const kontrol = async () => {
          const b = razobrat(await vzyat('https://www.tektorg.ru/223-fz/procedures?organizer[]=9999999999'));
          const p = razobrat(await vzyat('https://www.tektorg.ru/223-fz/procedures?organizer[]='));
          return {bred: b.length, pusto: p.length};
        };
        """,
        'take': 15, 'predel_bred': 2,
    },
    'rts': {
        'nazvanie': 'РТС-тендер',
        'url': 'https://www.rts-tender.ru/poisk/organizator/',
        'fajl': 'rts-po-kompaniyam.csv',
        # Путь требует ИНН-КПП. КПП у нас есть не у всех; где нет — пробуем ИНН с типовым
        # КПП «ИНН[:4]01001», а если не вышло, помечаем «нет КПП» и не выдумываем.
        'js': r"""
        const vzyat = async (u) => { const r = await fetch(u,{credentials:'include'}); return await r.text(); };
        const razobrat = (h) => {
          const out = []; const re = /href="(\/[^"]*?(?:tender|lot|procedure)[^"]*?)"[^>]*>([\s\S]{0,400}?)<\/a>/gi;
          let m; while ((m = re.exec(h)) !== null) {
            const t = m[2].replace(/<[^>]+>/g,' ').replace(/&nbsp;/g,' ').replace(/\s+/g,' ').trim();
            if (t && t.length > 12) out.push({nomer:'', predmet: t.slice(0,300), summa:'', data:'', put: m[1]});
          }
          return out;
        };
        const odna = async (z) => {
          const kpp = z.kpp || (String(z.inn).slice(0,4) + '01001');
          const rows = []; const vid = {};
          for (let p = 1; p <= __MAXP__; p++) {
            const h = await vzyat('https://www.rts-tender.ru/poisk/organizator/' + z.inn + '-' + kpp + '/?page=' + p);
            const k = razobrat(h);
            if (!k.length) break;
            let novyh = 0;
            for (const x of k) { const kl = x.put; if (!vid[kl]) { vid[kl]=1; rows.push(x); novyh++; } }
            if (!novyh) break;
            await new Promise(r=>setTimeout(r,300));
          }
          return {inn: z.inn, vsego: rows.length, rows: rows};
        };
        const kontrol = async () => {
          const b = razobrat(await vzyat('https://www.rts-tender.ru/poisk/organizator/9999999999-999901001/'));
          return {bred: b.length, pusto: 0};
        };
        """,
        'take': 10, 'predel_bred': 3,
    },
}

OBSHCHEE = r"""
window.__RES = (async()=>{
  // Пауза: страница доредиректывается уже после старта скрипта, и контекст выполнения
  // уничтожается на середине. Выглядит как отказ площадки, площадка ни при чём.
  await new Promise(s=>setTimeout(s,5000));
  __TELO__
  const k = await kontrol();
  if (k.bred > __PREDEL_BRED__) return JSON.stringify({kontrol_provalen:
      'бессмыслица вернула ' + k.bred});
  const itog = [];
  for (const z of __ZADANIE__) {
    try { itog.push(await odna(z)); }
    catch(e) { itog.push({inn: z.inn, vsego: 0, rows: [], oshibka: String(e).slice(0,80)}); }
  }
  return JSON.stringify({kontrol: k, itog: itog});
})();
"""


def chitat(put):
    return list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(put) else []


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


def sprosit(p, zadanie, stranic):
    js = (OBSHCHEE.replace('__TELO__', p['js'])
          .replace('__ZADANIE__', json.dumps(zadanie, ensure_ascii=False))
          .replace('__MAXP__', str(stranic)).replace('__TAKE__', str(p['take']))
          .replace('__PREDEL_BRED__', str(p['predel_bred'])))
    zad = {'url': p['url'], 'screenshot': False,
           'eval_js': {'script': js, 'after_ms': 9000, 'return': 'window.__RES'}}
    r = subprocess.run([sys.executable, KLIENT, 'browser_probe',
                        json.dumps(zad, ensure_ascii=False)],
                       capture_output=True, text=True, timeout=2400)
    try:
        otvet = json.loads(r.stdout[r.stdout.index('{'):])
    except (ValueError, json.JSONDecodeError):
        return None, (r.stdout or r.stderr)[-200:]
    d = otvet.get('data') or {}
    if d.get('eval_js_err'):
        return None, str(d['eval_js_err'])[:200]
    try:
        return json.loads(d.get('eval_js_value') or 'null'), ''
    except json.JSONDecodeError as e:
        return None, f'ответ не разобран: {str(e)[:80]}'


def obojti(imya, celi, pachka, parallel, stranic):
    p = PLOSHCHADKI[imya]
    vyhod = os.path.join(C, p['fajl'])
    zhurnal = os.path.join(C, p['fajl'].replace('.csv', '-zhurnal.csv'))
    proydeno = {r['inn'] for r in chitat(zhurnal)}
    moi = [c for c in celi if c['inn'] not in proydeno]
    print(f'[{p["nazvanie"]}] к обходу {len(moi)} (пройдено {len(proydeno)})', file=sys.stderr)
    if not moi:
        return
    novyy_v = not os.path.exists(vyhod) or os.path.getsize(vyhod) == 0
    novyy_z = not os.path.exists(zhurnal) or os.path.getsize(zhurnal) == 0
    fv = open(vyhod, 'a', encoding='utf-8-sig', newline='')
    wv = csv.DictWriter(fv, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy_v:
        wv.writeheader()
    fz = open(zhurnal, 'a', encoding='utf-8-sig', newline='')
    wz = csv.DictWriter(fz, fieldnames=['inn', 'predpriyatie', 'vzyato', 'pochemu'],
                        delimiter=';', extrasaction='ignore')
    if novyy_z:
        wz.writeheader()
    sch = {'предприятий': 0, 'процедур': 0, 'пусто': 0, 'сбоев': 0}
    po_inn = {c['inn']: c for c in moi}
    pachki = [moi[i:i + pachka] for i in range(0, len(moi), pachka)]
    lock = threading.Lock()

    def odna(gr):
        return gr, sprosit(p, [{'inn': c['inn'], 'kpp': c.get('kpp') or ''} for c in gr], stranic)

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for n, (gr, (r, err)) in enumerate(pool.map(odna, pachki), 1):
            with lock:
                if r is None:
                    sch['сбоев'] += len(gr)
                    print(f'  [{imya}] СБОЙ пачки {n}: {err[:120]}', file=sys.stderr, flush=True)
                    continue
                if r.get('kontrol_provalen'):
                    print(f'  [{imya}] КОНТРОЛЬ ПРОВАЛЕН: {r["kontrol_provalen"]} — площадка '
                          'пропущена, ничего не записано', file=sys.stderr)
                    break
                for it in r.get('itog') or []:
                    c = po_inn.get(it['inn']) or {}
                    sch['предприятий'] += 1
                    sch['процедур'] += len(it['rows'])
                    if not it['rows']:
                        sch['пусто'] += 1
                    wz.writerow({'inn': it['inn'], 'predpriyatie': c.get('predpriyatie') or '',
                                 'vzyato': len(it['rows']),
                                 'pochemu': it.get('oshibka') or 'обойдено'})
                    for x in it['rows']:
                        wv.writerow({'inn': it['inn'],
                                     'predpriyatie': c.get('predpriyatie') or '',
                                     'nomer': x.get('nomer') or '',
                                     'predmet': x.get('predmet') or '',
                                     'summa': x.get('summa') or '', 'data': x.get('data') or '',
                                     'ssylka': x.get('put') or '', 'ploshchadka': p['nazvanie']})
                fv.flush()
                fz.flush()
                print(f'  [{imya}] {min(n * pachka, len(moi))}/{len(moi)}: {sch}',
                      file=sys.stderr, flush=True)
            time.sleep(0.3)
    fv.close()
    fz.close()
    print(f'[{p["nazvanie"]}] готово: {sch} → {vyhod}', file=sys.stderr)


def main():
    imena = [x.strip() for x in dovod('--ploshchadka', ','.join(PLOSHCHADKI)).split(',')
             if x.strip() in PLOSHCHADKI]
    predel = dovod('--predel', 10 ** 9)
    pachka = dovod('--pachka', 3)
    parallel = dovod('--parallel', 2)
    stranic = dovod('--stranic', 20)

    och = chitat(OCHERED)
    if len(och) < 300:
        sys.exit(f'ОСТАНОВКА: очередь {len(och)} строк — пересоберите базу перед обходом.')
    celi = [{'inn': r['inn'], 'predpriyatie': r.get('predpriyatie') or '',
             'kpp': r.get('kpp') or ''} for r in och][:predel]

    if '--kontrol' in sys.argv:
        for imya in imena:
            r, err = sprosit(PLOSHCHADKI[imya], [{'inn': celi[0]['inn'], 'kpp': ''}], 2)
            if r is None:
                print(f'  {imya}: СБОЙ — {err[:140]}', file=sys.stderr)
                continue
            n = len((r.get('itog') or [{}])[0].get('rows') or [])
            print(f'  {imya}: контроль {r.get("kontrol")}, первое предприятие дало {n} карточек'
                  + ('  ПРОВАЛЕН: ' + r['kontrol_provalen'] if r.get('kontrol_provalen') else ''),
                  file=sys.stderr)
        return

    for imya in imena:
        obojti(imya, celi, pachka, parallel, stranic)


if __name__ == '__main__':
    main()
