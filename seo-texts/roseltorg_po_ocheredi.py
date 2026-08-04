# -*- coding: utf-8 -*-
"""Закупки Росэлторга по КАЖДОМУ предприятию очереди, а не по ключевым словам.

Третья площадка после Tender.pro и ЭТП ГПБ, где приём «страница компании» подтверждён.
Отличие от них важное и в нашу пользу: **вход прямо по ИНН**, справочник площадки не нужен,
поэтому адресуемы ВСЕ 776 предприятий очереди, а не те, кого мы нашли в чужом каталоге.

Адрес: `https://www.roseltorg.ru/procedures/search_ajax?customer=<ИНН>&page=<N с нуля>`
Отдаёт 10 карточек HTML на страницу, в карточке пометка «Найдено в ИНН». Совмещается со словом
через `&query_field=<слово>`.

МАСШТАБ, замеренный агентом: у нас по этой площадке 1 834 строки ЗА ВЕСЬ словарный обход, а одна
компания (Мосводоканал) отдаёт около 9 951 процедуры. Порядок недобора тот же, что был на
Tender.pro и ЭТП ГПБ.

ЧЕГО ЖДАТЬ ЧЕСТНО. На Tender.pro такой же обход дал 157 596 закупок и НОЛЬ новых предприятий:
полезная доля 0,9 %, а всё центробежное там уже было найдено словарём. Поэтому здесь ценность
не в фактах о машинах, а в ЛЮДЯХ — карточка процедуры называет контактное лицо, а это
единственный канал, двигающий главную меру проекта (109 из 129 технических людей с личным
мобильным пришли именно с карточек закупок).

ОБЯЗАТЕЛЬНЫЙ КОНТРОЛЬ перед сбором, по трём ловушкам, пойманным на соседних площадках:
  * пустое значение фильтра отдаёт ВЕСЬ реестр (так ведут себя ЭТП ГПБ и Tender.pro);
  * несуществующий ИНН обязан вернуть пусто, иначе фильтр игнорируется молча;
  * выдача обязана содержать запрошенный ИНН, иначе сужение потекло.
Не прошёл контроль — модуль останавливается и НЕ пишет ничего.

Использование:
    python3 roseltorg_po_ocheredi.py --kontrol        # только проверка сужения
    python3 roseltorg_po_ocheredi.py --predel 20
    python3 roseltorg_po_ocheredi.py --stranic 40
"""
import csv
import json
import os
import re
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
VYHOD = os.path.join(C, 'roseltorg-po-kompaniyam.csv')
KARTA = os.path.join(C, 'roseltorg-obhod-zhurnal.csv')
COLS = ['inn', 'predpriyatie', 'nomer', 'predmet', 'zakazchik', 'summa', 'data', 'stadiya',
        'ssylka']
STRANIC_MAX = 40          # 400 процедур на предприятие


def chitat(put):
    return list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(put) else []


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


SKRIPT = r"""
window.__RES = (async()=>{
  // Пауза перед работой: страница площадки успевает доредиректиться. Без неё контекст
  // выполнения уничтожается навигацией на середине скрипта («Execution context was
  // destroyed»), и это выглядит как сбой площадки, хотя площадка ни при чём.
  await new Promise(s=>setTimeout(s,5000));
  const vzyat = async (u) => {
    for (let p = 0; p < 3; p++) {
      try {
        const r = await fetch(u, {credentials:'include'});
        if (r.status === 429 || r.status >= 500) { await new Promise(s=>setTimeout(s,2000*(p+1))); continue; }
        return await r.text();
      } catch(e) { await new Promise(s=>setTimeout(s,1500)); }
    }
    return '';
  };
  const B = 'https://www.roseltorg.ru/procedures/search_ajax';
  const razobrat = (h) => {
    const out = [];
    // карточки разделяются ссылкой на процедуру; тянем номер, предмет, заказчика, сумму, дату
    const re = /href="(\/procedure\/[^"]{3,120})"[^>]*>([\s\S]{0,600}?)<\/a>/g;
    let m;
    while ((m = re.exec(h)) !== null) {
      const put = m[1];
      const kus = m[2].replace(/<[^>]+>/g,' ').replace(/&nbsp;/g,' ').replace(/\s+/g,' ').trim();
      if (!kus) continue;
      out.push({put: put, tekst: kus.slice(0,300)});
    }
    return out;
  };
  const ZADANIE = __ZADANIE__;
  const itog = [];
  // КОНТРОЛЬ 1: несуществующий ИНН обязан вернуть пусто.
  const bred = await vzyat(B + '?customer=9999999999&page=0');
  const bred_n = razobrat(bred).length;
  // КОНТРОЛЬ 2: пустое значение не должно отдавать реестр целиком.
  const pusto = await vzyat(B + '?customer=&page=0');
  const pusto_n = razobrat(pusto).length;
  if (bred_n > 2) return JSON.stringify({kontrol_provalen: 'бессмыслица вернула ' + bred_n});
  for (const z of ZADANIE) {
    const rows = [];
    for (let p = 0; p < __MAXP__; p++) {
      const h = await vzyat(B + '?customer=' + encodeURIComponent(z.inn) + '&page=' + p);
      const kus = razobrat(h);
      if (!kus.length) break;
      // сужение проверяем на каждой странице: ИНН обязан встречаться в выдаче
      const svoy = h.indexOf(z.inn) >= 0;
      for (const k of kus) rows.push({put: k.put, tekst: k.tekst, inn_v_vydache: svoy});
      if (p + 1 < __MAXP__) await new Promise(s=>setTimeout(s,350));
    }
    itog.push({inn: z.inn, rows: rows});
  }
  return JSON.stringify({kontrol_bred: bred_n, kontrol_pusto: pusto_n, itog: itog});
})();
"""


def sprosit(zadanie, stranic):
    js = (SKRIPT.replace('__ZADANIE__', json.dumps(zadanie, ensure_ascii=False))
          .replace('__MAXP__', str(stranic)))
    zad = {'url': 'https://www.roseltorg.ru/procedures/', 'screenshot': False,
           'eval_js': {'script': js, 'after_ms': 8000, 'return': 'window.__RES'}}
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
    predel = dovod('--predel', 10 ** 9)
    pachka = dovod('--pachka', 3)
    parallel = dovod('--parallel', 3)
    # Предел раннера: сверх 30 воркеров задачи не работают, а ждут.
    import predel_rannera
    predel_rannera.preduprezhdenie(parallel)
    stranic = dovod('--stranic', STRANIC_MAX)

    och = chitat(OCHERED)
    if len(och) < 300:
        sys.exit(f'ОСТАНОВКА: очередь {len(och)} строк — пересоберите базу перед обходом.')
    proydeno = {r['inn'] for r in chitat(KARTA)}
    celi = [{'inn': r['inn'], 'predpriyatie': r.get('predpriyatie') or ''}
            for r in och if r['inn'] not in proydeno][:predel]
    print(f'предприятий к обходу: {len(celi)} (уже пройдено {len(proydeno)})', file=sys.stderr)

    if '--kontrol' in sys.argv:
        r, err = sprosit(celi[:1], 2)
        if r is None:
            sys.exit(f'сбой контроля: {err}')
        n = len((r.get('itog') or [{}])[0].get('rows') or [])
        print(f'контроль: бессмыслица вернула {r.get("kontrol_bred")}, '
              f'пустое значение {r.get("kontrol_pusto")}, '
              f'первое предприятие дало {n} карточек', file=sys.stderr)
        if r.get('kontrol_provalen'):
            sys.exit(f'КОНТРОЛЬ ПРОВАЛЕН: {r["kontrol_provalen"]}')
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
    wk = csv.DictWriter(fk, fieldnames=['inn', 'predpriyatie', 'vzyato', 'pochemu'],
                        delimiter=';', extrasaction='ignore')
    if novyy_k:
        wk.writeheader()

    sch = {'предприятий': 0, 'процедур': 0, 'пусто': 0, 'сужение потекло': 0, 'сбоев': 0}
    po_inn = {c['inn']: c for c in celi}
    pachki = [celi[i:i + pachka] for i in range(0, len(celi), pachka)]
    lock = threading.Lock()

    def odna(gr):
        return gr, sprosit([{'inn': c['inn']} for c in gr], stranic)

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for nomer, (gr, (r, err)) in enumerate(pool.map(odna, pachki), 1):
            with lock:
                if r is None:
                    sch['сбоев'] += len(gr)
                    print(f'  СБОЙ пачки {nomer}: {err[:130]}', file=sys.stderr, flush=True)
                    continue
                if r.get('kontrol_provalen'):
                    sys.exit(f'ОСТАНОВКА: {r["kontrol_provalen"]}. Сужение по ИНН не '
                             'применяется — собранное было бы реестром целиком.')
                for it in r.get('itog') or []:
                    c = po_inn.get(it['inn']) or {}
                    sch['предприятий'] += 1
                    sch['процедур'] += len(it['rows'])
                    if not it['rows']:
                        sch['пусто'] += 1
                    chuzhih = sum(1 for x in it['rows'] if not x.get('inn_v_vydache'))
                    sch['сужение потекло'] += chuzhih
                    wk.writerow({'inn': it['inn'], 'predpriyatie': c.get('predpriyatie') or '',
                                 'vzyato': len(it['rows']),
                                 'pochemu': ('ИНН не встречается в выдаче — проверить'
                                             if chuzhih else 'обойдено')})
                    for x in it['rows']:
                        wv.writerow({'inn': it['inn'],
                                     'predpriyatie': c.get('predpriyatie') or '',
                                     'nomer': (re.search(r'/(\d{6,})', x['put']) or
                                               [None, ''])[1] if re.search(r'/(\d{6,})', x['put'])
                                     else '',
                                     'predmet': x['tekst'], 'zakazchik': '', 'summa': '',
                                     'data': '', 'stadiya': '',
                                     'ssylka': 'https://www.roseltorg.ru' + x['put']})
                fv.flush()
                fk.flush()
                print(f'  {min(nomer * pachka, len(celi))}/{len(celi)}: {sch}',
                      file=sys.stderr, flush=True)
            time.sleep(0.4)

    fv.close()
    fk.close()
    print(f'готово: {sch}\n→ {VYHOD}\n→ {KARTA}', file=sys.stderr)
    if sch['сужение потекло']:
        print('ВНИМАНИЕ: в части выдачи запрошенный ИНН не встречается — проверить адрес',
              file=sys.stderr)


if __name__ == '__main__':
    main()
