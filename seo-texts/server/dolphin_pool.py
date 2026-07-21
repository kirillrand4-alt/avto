# -*- coding: utf-8 -*-
"""Пул персистентных Dolphin-браузеров для массового пробоя защищённых сайтов.

Идея (ответ на «не закрывать сессию после 1 сайта, крутить потоком»):
профиль стартует ОДИН раз и переиспользуется на МНОГО сайтов подряд — стартовая
цена (~15-20с) платится раз на профиль, а не на каждый сайт. N профилей крутятся
ПАРАЛЛЕЛЬНО через multiprocessing (каждый профиль = свой процесс + свой Playwright,
без общего состояния — sync-Playwright не падает, как падал в потоках).

Каждый воркер: старт профиля -> CDP -> одна вкладка -> цикл по своей пачке сайтов
(goto -> контент -> добор контактов + provider-роли) -> стоп профиля в конце.
Результаты пишутся в enrich.db (по ИНН) и возвращаются сводкой.

args (stdin JSON): {companies:[{inn,name,city,site?}], dolphin_token, dolphin_profiles:[id],
                    per_site_wait_ms?, write_db?, use_provider?}
"""
import os, sys, json, time, re
import multiprocessing as mp

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)


def _worker(profile_id, token, companies, opts, out_path):
    """Один процесс: держит профиль открытым, гоняет через него свою пачку сайтов."""
    import enrich_contacts as EC
    import browser_probe as BP
    results = []
    wait_ms = int(opts.get('per_site_wait_ms', 7000))
    use_provider = opts.get('use_provider', True)
    browser = None
    # инкрементальная запись СРАЗУ, разными способами (переживает падение процесса):
    # (1) свой jsonl на процесс (append), (2) SQLite (своё соединение, WAL-локи).
    _jsonl = None
    _db = None
    if opts.get('write_db', True):
        try:
            _jsonl = open(os.path.join(DIR, f'enrich_stream_pool_{profile_id}.jsonl'), 'a', encoding='utf-8')
        except Exception:  # noqa: BLE001
            _jsonl = None
        try:
            import enrich_db as EDB
            _db = EDB.EnrichDB()
        except Exception:  # noqa: BLE001
            _db = None

    def _persist(r):
        if _jsonl is not None:
            try:
                _jsonl.write(json.dumps(r, ensure_ascii=False) + '\n')
                _jsonl.flush()
                os.fsync(_jsonl.fileno())
            except Exception:  # noqa: BLE001
                pass
        if _db is not None and r.get('inn'):
            try:
                _db.upsert_company(str(r['inn']), name=r.get('name'), site=r.get('site'),
                                   activity=r.get('activity'), is_competitor=r.get('is_competitor'),
                                   best_email=r.get('best_for_outreach'), phones=r.get('phones'))
                for e in (r.get('emails') or []):
                    if e.get('email'):
                        _db.add_email(str(r['inn']), e.get('email', ''), role=e.get('role', ''),
                                      person=e.get('person', ''), source='dolphin-pool')
            except Exception:  # noqa: BLE001
                pass
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            cdp_ep, _port = BP.dolphin_start(profile_id, headless=False, token=token)
            browser = p.chromium.connect_over_cdp(cdp_ep)
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            for c in companies:
                r = {'inn': c.get('inn'), 'name': c.get('name')}
                try:
                    site = c.get('site')
                    src = 'given'
                    if not site:
                        site, src, _card = EC.find_site_via_xmlriver(c)
                    if not site:
                        r['error'] = 'сайт не найден'
                        results.append(r)
                        continue
                    if not site.startswith('http'):
                        site = 'http://' + site
                    r['site'] = EC._domain(site)
                    r['site_source'] = src
                    t0 = time.time()
                    page.goto(site, timeout=45000, wait_until='domcontentloaded')
                    page.wait_for_timeout(wait_ms)
                    html = page.content()
                    r['crawl_sec'] = round(time.time() - t0, 1)
                    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.S | re.I)
                    text = re.sub(r'<[^>]+>', ' ', text)
                    text = re.sub(r'\s+', ' ', text)
                    h_em, h_ph = EC._harvest_from_html(html)
                    if h_em or h_ph:
                        text += ' Контакты(добор): ' + ' '.join(sorted(h_em)) + ' ' + ' '.join(sorted(h_ph))
                    if use_provider and EC.EMAIL_RE.search(text):
                        data, how = EC.extract_roles(text[:24000], c)
                    else:
                        ems = sorted(set(e.lower() for e in EC.EMAIL_RE.findall(text)
                                     if not e.lower().endswith(EC._IMG_EXT)))
                        data = {'emails': [{'email': e, 'role': 'общий'} for e in ems[:8]],
                                'best_for_outreach': ems[0] if ems else '', 'phones': sorted(h_ph)}
                        how = 'regex'
                    r['emails'] = data.get('emails', [])
                    r['best_for_outreach'] = data.get('best_for_outreach', '')
                    r['phones'] = data.get('phones') or sorted(h_ph)
                    r['activity'] = data.get('activity')
                    r['is_competitor'] = data.get('is_compressor_maker')
                    r['how'] = how
                except Exception as e:  # noqa: BLE001
                    r['error'] = f'{type(e).__name__}:{str(e)[:80]}'
                _persist(r)   # пишем СРАЗУ, не в конце
                results.append(r)
            try:
                if _jsonl is not None:
                    _jsonl.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                browser.close()
            except Exception:  # noqa: BLE001
                pass
    except Exception as e:  # noqa: BLE001
        results.append({'profile': profile_id, 'fatal': str(e)[:150]})
    finally:
        try:
            BP.dolphin_stop(profile_id, token=token)
        except Exception:  # noqa: BLE001
            pass
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False)


def main():
    try:
        args = json.load(sys.stdin)
    except Exception:
        args = {}
    companies = args.get('companies', [])
    token = args.get('dolphin_token', '') or os.environ.get('DOLPHIN_TOKEN', '')
    profiles = args.get('dolphin_profiles', []) or []
    if not companies or not token or not profiles:
        print(json.dumps({'error': 'нужны companies + dolphin_token + dolphin_profiles'}))
        return
    n = min(len(profiles), max(1, int(args.get('workers', len(profiles)))))
    profiles = profiles[:n]
    # раскидать компании по профилям (round-robin)
    chunks = [[] for _ in range(n)]
    for i, c in enumerate(companies):
        chunks[i % n].append(c)
    opts = {'per_site_wait_ms': args.get('per_site_wait_ms', 7000),
            'use_provider': args.get('use_provider', True)}
    procs, outs = [], []
    for i in range(n):
        outp = os.path.join(DIR, f'.pool_out_{i}.json')
        outs.append(outp)
        pr = mp.Process(target=_worker, args=(str(profiles[i]), token, chunks[i], opts, outp))
        pr.start()
        procs.append(pr)
    for pr in procs:
        pr.join(timeout=int(args.get('total_timeout', 1500)))
    # собрать результаты
    results = []
    for outp in outs:
        try:
            results.extend(json.load(open(outp, encoding='utf-8')))
            os.remove(outp)
        except Exception:  # noqa: BLE001
            pass
    saved = 0
    if args.get('write_db', True):
        try:
            import enrich_db as EDB
            db = EDB.EnrichDB()
            for r in results:
                inn = str(r.get('inn') or '')
                if not inn:
                    continue
                db.upsert_company(inn, name=r.get('name'), site=r.get('site'),
                                  activity=r.get('activity'), is_competitor=r.get('is_competitor'),
                                  best_email=r.get('best_for_outreach'), phones=r.get('phones'))
                for e in (r.get('emails') or []):
                    if e.get('email'):
                        db.add_email(inn, e.get('email', ''), role=e.get('role', ''),
                                     person=e.get('person', ''), source='dolphin-pool')
                saved += 1
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f'db skip: {str(e)[:100]}\n')
    with_email = sum(1 for r in results if r.get('emails'))
    print(json.dumps({'results': results, 'count': len(results),
                      'summary': {'profiles': n, 'with_email': with_email, 'saved_to_db': saved}},
                     ensure_ascii=False))


if __name__ == '__main__':
    mp.freeze_support()
    main()
