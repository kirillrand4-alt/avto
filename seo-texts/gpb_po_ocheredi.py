# -*- coding: utf-8 -*-
"""Закупки ЭТП ГПБ по КАЖДОМУ предприятию очереди, а не по ключевым словам.

Тот же приём, что вытащил Tender.pro из «канал выжат»: обход по словам берёт то, что попало под
десяток формулировок, а страница компании показывает всё, что она вообще закупала.

ЗАМЕР, из-за которого модуль появился (03.08, проверено своими руками через раннер):
    без фильтра                                          1 724 204 процедуры
    procedure[customers][2]=Газпром добыча Оренбург           2 567
    то же, но значение ПУСТОЕ                            1 724 204  ← фильтр молча игнорируется
    контроль бессмыслицей                                     пусто
Весь наш файл по этой площадке — 906 строк. Одна компания даёт втрое больше.

ЛОВУШКА, ровно как `block=tenders` на Tender.pro: если значение фильтра оставить пустым,
площадка МОЛЧА отдаёт весь реестр. Без контроля это выглядит как «обход собрал 1,7 миллиона
закупок», и в панель уехал бы весь реестр страны. Поэтому:
  * значение (название компании) обязательно, пустое — отказ до запроса;
  * перед прогоном делается контрольный запрос бессмыслицей, и если он вернёт не пусто,
    модуль останавливается: значит сужение не применяется и собирать нечего.

ВХОД БЕСПЛАТНЫЙ: `company_id` площадки уже лежит у нас в `centro/etpgpb-zakazchiki-inn.csv`
(17 499 организаций с ИНН, КПП и slug). По очереди 776 предприятий совпадает 337 строк на
259 предприятий — их и обходим, добывать входы не надо.

Ключ фильтра — company_id, а значение — название. И то и другое берётся из справочника, поэтому
опечатка в названии невозможна: она означала бы пустую выдачу, а не чужую.

Использование:
    python3 gpb_po_ocheredi.py                 # вся очередь
    python3 gpb_po_ocheredi.py --predel 20     # первые 20 предприятий
    python3 gpb_po_ocheredi.py --kontrol       # только проверка сужения, без сбора
"""
import csv
import json
import os
import subprocess
import sys
import time

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
C = os.path.join(L, 'centro')
KLIENT = os.path.join(BAZA, 'server', 'run_on_server.py')
SPRAVOCHNIK = os.path.join(C, 'etpgpb-zakazchiki-inn.csv')
OCHERED = os.path.join(L, 'OCHERED-centrobezhnye.csv')
VYHOD = os.path.join(C, 'etpgpb-po-kompaniyam.csv')
KARTA = os.path.join(C, 'etpgpb-obhod-zhurnal.csv')
COLS = ['inn', 'predpriyatie', 'company_id', 'procedure_id', 'nomer', 'predmet', 'vid',
        'sekciya', 'summa', 'data', 'stadiya', 'ssylka']
# Сколько процедур одной компании берём. 200 — предел `per`, 400 страниц — жёсткий потолок
# площадки (`total_pages: 400`), дальше она не пускает никого.
NA_STRANICE = 200
STRANIC_MAX = 20         # 4 000 процедур на секцию; у самой крупной компании нашего списка
                         # 3 868 всего, так что потолок с запасом

# СЕКЦИИ ПЛОЩАДКИ, снято с разметки её же страницы. Спрашиваются ПО ОДНОЙ, и вот почему.
# Замер 03.08 на «Газпром добыча Оренбург» (всего без фильтра 2 567):
#     fz223 878 | commerce 937 | gazprom 1 630 | nelikvid 213 | trade_portal 722 | прочие 0
#     две секции сразу (fz223 + gazprom) → 1 630, то есть РОВНО gazprom
# **При нескольких секциях применяется только ПОСЛЕДНЯЯ.** Это третья по счёту ловушка того же
# рода на этой площадке: пустое значение отдаёт весь реестр, `kind`/`type`/`sale` игнорируются
# молча, перечень секций молча схлопывается в одну. Все три выглядят как работающий фильтр.
# Сумма по секциям 4 380 против 2 567 — процедура принадлежит нескольким секциям сразу,
# поэтому дедуп по procedure_id обязателен, иначе треть строк задвоится.
SEKCII = ['fz223', 'commerce', 'gazprom', 'trade_portal', 'zakupki_biznes', 'hydrocarbons',
          'pao_gazpromneft', 'geh_group', 'inter_rao', 'drilling', 'nelikvid']


def chitat(put):
    return list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(put) else []


SKRIPT = r"""
window.__RES = (async()=>{
  const q = async (u) => {
    for (let popytka = 0; popytka < 3; popytka++) {
      try {
        const r = await fetch(u, {headers:{'Accept':'application/json'}});
        if (r.status === 429 || r.status >= 500) { await new Promise(s=>setTimeout(s, 2000*(popytka+1))); continue; }
        return await r.json();
      } catch(e) { await new Promise(s=>setTimeout(s, 1500)); }
    }
    return null;
  };
  const B = 'https://etpgpb.ru/api/v2/procedures/?sort=by_relevance&procedure[stage][0]=all';
  const SEKCII = __SEKCII__;
  const ZADANIE = __ZADANIE__;
  const itog = [];
  // КОНТРОЛЬ ПЕРЕД СБОРОМ: несуществующая компания обязана вернуть пусто.
  const bred = await q(B + '&page=1&per=1&procedure[customers][99999999]=' + encodeURIComponent('ЮЮЮНЕСУЩЕСТВУЮЩАЯ'));
  const bred_total = (bred && bred.meta && bred.meta.total_count) || 0;
  if (bred_total > 100) return JSON.stringify({kontrol_provalen: bred_total});
  for (const z of ZADANIE) {
    const kl = '&procedure[customers][' + z.cid + ']=' + encodeURIComponent(z.name);
    const vidno = {};      // дедуп по id: процедура принадлежит нескольким секциям сразу
    let vsego_bez_sekcij = 0;
    const pervaya_bez = await q(B + '&page=1&per=1' + kl);
    vsego_bez_sekcij = (pervaya_bez && pervaya_bez.meta && pervaya_bez.meta.total_count) || 0;
    const po_sekciyam = {};
    for (const sek of SEKCII) {
      const ks = kl + '&procedure[section][0]=' + sek;
      const pervaya = await q(B + '&page=1&per=__PER__' + ks);
      const vsego = (pervaya && pervaya.meta && pervaya.meta.total_count) || 0;
      po_sekciyam[sek] = vsego;
      if (!vsego) continue;
      const stranic = Math.min(Math.ceil(vsego / __PER__), __MAXP__);
      for (let p = 1; p <= stranic; p++) {
        const j = (p === 1) ? pervaya : await q(B + '&page=' + p + '&per=__PER__' + ks);
        for (const d of ((j && j.data) || [])) {
          if (vidno[d.id]) continue;
          const a = d.attributes || {};
          // Продажи отсеиваем ПО ПУТИ, а не по секции: `commerce` содержит и закупки, и торги,
          // а `trade_portal` вопреки названию — закупки. Путь называет вид прямо.
          const prodazha = /\/sale\//.test(a.truncated_path || '');
          vidno[d.id] = {id: d.id, nomer: a.registry_number || '',
                         predmet: (a.title || '').slice(0,300),
                         summa: String(a.amount || ''),
                         data: (a.date_published || '').slice(0,10),
                         stadiya: a.stage || '', sekciya: a.section_category_name || '',
                         put: (a.truncated_path || '').slice(0,160),
                         vid: prodazha ? 'продажа' : 'закупка'};
        }
        if (p < stranic) await new Promise(s=>setTimeout(s, 350));
      }
    }
    const rows = Object.values(vidno);
    itog.push({cid: z.cid, inn: z.inn, vsego: vsego_bez_sekcij,
               po_sekciyam: po_sekciyam, rows: rows});
  }
  return JSON.stringify({kontrol_bred: bred_total, itog: itog});
})();
"""


def sprosit(zadanie):
    """Одна пачка компаний за одно задание раннера. Таймаут раннера 1 800 с — держим пачку
    маленькой: лучше десять коротких заданий, чем одно, убитое на девятой компании."""
    js = (SKRIPT.replace('__ZADANIE__', json.dumps(zadanie, ensure_ascii=False))
          .replace('__SEKCII__', json.dumps(SEKCII, ensure_ascii=False))
          .replace('__PER__', str(NA_STRANICE)).replace('__MAXP__', str(STRANIC_MAX)))
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
    predel = int(sys.argv[sys.argv.index('--predel') + 1]) if '--predel' in sys.argv else 10 ** 9
    pachka = int(sys.argv[sys.argv.index('--pachka') + 1]) if '--pachka' in sys.argv else 4

    spravochnik = chitat(SPRAVOCHNIK)
    if len(spravochnik) < 1000:
        sys.exit(f'ОСТАНОВКА: {SPRAVOCHNIK} — {len(spravochnik)} строк, ожидалось 17 000+. '
                 'Без справочника company_id обход невозможен.')
    och = {r['inn']: r for r in chitat(OCHERED)}
    if len(och) < 300:
        sys.exit(f'ОСТАНОВКА: очередь {len(och)} строк — пересоберите базу перед обходом.')

    celi, vidano = [], set()
    for r in spravochnik:
        inn = (r.get('inn') or '').strip()
        cid = (r.get('company_id') or '').strip()
        name = (r.get('name') or '').strip()
        # Название ОБЯЗАТЕЛЬНО: пустое значение фильтра означает «весь реестр», а не «эта
        # компания». Такую строку пропускаем молча нельзя — считаем и печатаем.
        if inn not in och or not cid or not name or (inn, cid) in vidano:
            continue
        vidano.add((inn, cid))
        celi.append({'inn': inn, 'cid': cid, 'name': name[:120],
                     'predpriyatie': och[inn].get('predpriyatie') or name})
    bez_nazvaniya = sum(1 for r in spravochnik if (r.get('inn') or '').strip() in och
                        and not (r.get('name') or '').strip())
    proydeno = {r['company_id'] for r in chitat(KARTA)}
    celi = [c for c in celi if c['cid'] not in proydeno][:predel]
    print(f'входов из справочника: {len(celi)} (уже пройдено {len(proydeno)}), '
          f'пропущено без названия: {bez_nazvaniya}', file=sys.stderr)

    if '--kontrol' in sys.argv:
        r, err = sprosit([celi[0]] if celi else [])
        print(json.dumps(r, ensure_ascii=False)[:600] if r else f'сбой: {err}', file=sys.stderr)
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
    wk = csv.DictWriter(fk, fieldnames=['inn', 'company_id', 'predpriyatie', 'vsego_na_ploshchadke',
                                        'vzyato', 'zakupok', 'po_sekciyam', 'pochemu'],
                        delimiter=';', extrasaction='ignore')
    if novyy_k:
        wk.writeheader()

    sch = {'компаний': 0, 'закупок': 0, 'продаж (не наше)': 0, 'пусто у компании': 0, 'сбоев': 0}
    po_cid = {c['cid']: c for c in celi}
    for i in range(0, len(celi), pachka):
        gr = celi[i:i + pachka]
        r, err = sprosit([{'cid': c['cid'], 'inn': c['inn'], 'name': c['name']} for c in gr])
        if r is None:
            sch['сбоев'] += len(gr)
            print(f'  СБОЙ пачки {i // pachka + 1}: {err[:140]}', file=sys.stderr, flush=True)
            continue
        if r.get('kontrol_provalen'):
            sys.exit(f'ОСТАНОВКА: контроль бессмыслицей вернул {r["kontrol_provalen"]} процедур. '
                     'Значит сужение по компании НЕ применяется, и всё собранное было бы реестром '
                     'целиком, а не закупками предприятия. Проверьте ключ фильтра.')
        for it in r.get('itog') or []:
            c = po_cid.get(str(it['cid'])) or {}
            sch['компаний'] += 1
            sch['закупок'] += sum(1 for x in it['rows'] if x.get('vid') != 'продажа')
            sch['продаж (не наше)'] += sum(1 for x in it['rows'] if x.get('vid') == 'продажа')
            if not it['rows']:
                sch['пусто у компании'] += 1
            wk.writerow({'inn': it.get('inn') or c.get('inn') or '', 'company_id': it['cid'],
                         'predpriyatie': c.get('predpriyatie') or '',
                         'vsego_na_ploshchadke': it.get('vsego') or 0, 'vzyato': len(it['rows']),
                         'zakupok': sum(1 for x in it['rows'] if x.get('vid') != 'продажа'),
                         'po_sekciyam': json.dumps(
                             {k: v for k, v in (it.get('po_sekciyam') or {}).items() if v},
                             ensure_ascii=False)[:200],
                         'pochemu': ('взято не всё, потолок площадки'
                                     if (it.get('vsego') or 0) > len(it['rows']) else 'обойдено')})
            for x in it['rows']:
                wv.writerow({'inn': it.get('inn') or c.get('inn') or '',
                             'predpriyatie': c.get('predpriyatie') or '',
                             'company_id': it['cid'], 'procedure_id': x.get('id') or '',
                             'nomer': x.get('nomer') or '', 'predmet': x.get('predmet') or '',
                             'vid': x.get('vid') or '', 'sekciya': x.get('sekciya') or '',
                             'summa': x.get('summa') or '',
                             'data': x.get('data') or '', 'stadiya': x.get('stadiya') or '',
                             'ssylka': f'https://etpgpb.ru{x.get("put") or ""}'})
        fv.flush()
        fk.flush()
        print(f'  {min(i + pachka, len(celi))}/{len(celi)}: {sch}', file=sys.stderr, flush=True)
        time.sleep(0.5)

    fv.close()
    fk.close()
    print(f'готово: {sch}\n→ {VYHOD}\n→ {KARTA}', file=sys.stderr)


if __name__ == '__main__':
    main()
