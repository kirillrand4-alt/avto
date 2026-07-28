#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Регулярный news-скан (задача #49-б, п.1): один ИДЕМПОТЕНТНЫЙ прогон «обновить всё».

ПРОБЛЕМА: сигналы собирались разовыми sweep'ами — из 861 сигнала моложе 30 дней
было лишь 77, а 145 доноров без RSS вообще не опрашивались. Этот скрипт — ежедневная
инкрементальная подпитка (планировщик Windows, 07:00 МСК, см. setup-news-schedule.ps1):
опросить ВСЕХ живых доноров (RSS — у кого есть; остальным — лестница no_rss),
новые ссылки → seen_news, капекс-события → сигналы в enrich.db тем же конвейером,
что news_scan.py.

РЕЮЗ news_scan (импортом, не копипастой — правило задачи):
  _get/_rss_items/fresh — фетч и парсинг лент;  _news_key — канон-ключ дедупа;
  _CAPEX_KW — предфильтр заголовков (бережём fable от «погоды»);
  extract_event — капекс-классификация ПРОВАЙДЕРСКИМ API (fable, правило владельца:
  вся тяжёлая работа — через провайдера, свои LLM-вызовы не изобретаем);
  dadata_suggest / division_of — имя → ИНН → направление (kc/meyer).
Тонкая склейка вокруг них здесь своя, потому что в news_scan она живёт замыканиями
внутри main() (enrich_ev/_persist_event) и импортом не достаётся.

ИДЕМПОТЕНТНОСТЬ: повторный запуск безопасен — дедуп seen_news отсекает уже виденные
ссылки ДО провайдера (ноль лишних трат), signals защищена UNIQUE(inn,source,what),
а метрики прогона (scan_runs) честно покажут нули.

УСТОЙЧИВОСТЬ: каждый донор — в своём try/except; падение одного донора идёт в лог
и в fail_streak, прогон продолжается (жёсткое требование задачи)."""
import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Секреты (PROVIDER_API_KEY / DADATA_TOKEN / ...) должны попасть в окружение ДО
# импорта news_scan: его verify_company читает часть env при импорте. job_runner
# грузит runner-secrets.env побочным эффектом импорта — реюзаем его загрузчик,
# а не дублируем. В песочнице/тестах модуль может отсутствовать — это не ошибка.
try:
    import job_runner as _JR  # noqa: F401
except Exception:  # noqa: BLE001
    pass

import news_scan as NS
import enrich_db as EDB
import freshness
import no_rss
import schedule_db as SDB


def _log(msg):
    sys.stderr.write(time.strftime('[%H:%M:%S] ') + msg + '\n')
    sys.stderr.flush()


def _poll_rss_donor(fetcher, row, days):
    """Донор с ОБЪЯВЛЕННЫМ RSS (его нашла дискавери news_scan, donors.rss).
    Просто читаем ленту; парсер и правило свежести — news_scan (_rss_items/fresh).
    Идём через тот же вежливый фетчер, что и лестница: паузы/кап — единые."""
    body = fetcher.get(row['rss'])
    if not body:
        return None, 'fetch'
    items = []
    for it in NS._rss_items(body):
        if it.get('title') and it.get('link') and NS.fresh(it.get('pubDate', ''), days):
            items.append({'title': it['title'][:200], 'link': it['link'],
                          'pubDate': it.get('pubDate', '')})
    return items, ''


def _extract_one(db, item, token, lock, jsonl):
    """Капекс-извлечение ОДНОЙ новости — тот же путь, что enrich_ev/_persist_event
    в news_scan.main: провайдер (fable) → фильтр РФ → dadata (ИНН) → durable-запись
    (jsonl-сток + enrich.db). Вся тяжесть — импортированные NS.extract_event /
    NS.dadata_suggest; своего LLM здесь нет. Любой сбой — None (не ронять прогон)."""
    try:
        # Классификатору — полный текст статьи, не заголовок (слово владельца
        # 28.07: «и у не вк в том числе»): детали «какие линии» живут в теле.
        # hasattr — переживает старый news_scan на сервере без fetch_article.
        if hasattr(NS, 'fetch_article'):
            item = NS.fetch_article(dict(item))
        ev = NS.extract_event(item.get('full_text') or item['title'],
                              item.get('source', ''))
        if not ev or not ev.get('is_capex'):
            return None
        # только РФ — как в news_scan (в лентах мелькают Казахстан/Беларусь)
        ctry = str(ev.get('country', '')).lower()
        if ctry and not any(w in ctry for w in ('рф', 'росс', 'russia')):
            return None
        rec = {'title': item['title'], 'source_url': item['link'],
               'article_chars': item.get('article_chars', 0),
               'source_name': item.get('source', ''), 'published': item.get('pubDate', ''),
               'collector': item.get('collector', 'cron'),
               'event_type': ev.get('event_type'), 'what': ev.get('what'),
               'region': ev.get('region'), 'sum': ev.get('sum'),
               'hotness': ev.get('hotness'), 'company': ev.get('company'), 'is_capex': True}
        dd = NS.dadata_suggest(rec['company'], token)
        if dd:
            rec.update({'inn': dd['inn'], 'okved': dd['okved'], 'company_full': dd['name'],
                        'dd_region': dd['region'],
                        'egrul_emails': dd.get('egrul_emails') or [],
                        'inn_confidence': dd.get('confidence', '')})
            rec['division'] = NS.division_of(dd['okved'])
        # durable СРАЗУ (как _persist_event): переживает обрыв прогона на середине
        with lock:
            if jsonl is not None:
                try:
                    jsonl.write(json.dumps(rec, ensure_ascii=False) + '\n')
                    jsonl.flush()
                    os.fsync(jsonl.fileno())
                except Exception:  # noqa: BLE001
                    pass
            try:
                dm = re.match(r'https?://([^/]+)', rec.get('source_url') or '')
                if dm:  # частота донора накапливается durable — как в news_scan
                    db.bump_donor(dm.group(1).lstrip('www.'))
                inn = str(rec.get('inn') or '')
                if inn:
                    db.upsert_company(inn, name=rec.get('company_full') or rec.get('company'),
                                      division=rec.get('division'), okved=rec.get('okved'),
                                      region=rec.get('dd_region') or rec.get('region'))
                    db.add_signal(inn, source=rec.get('source_name') or 'news-cron',
                                  event_type=rec.get('event_type') or '',
                                  what=rec.get('what') or '',
                                  sum=str(rec.get('sum') or ''),
                                  source_url=rec.get('source_url') or '',
                                  hotness=int(rec.get('hotness') or 0),
                                  ts=rec.get('published') or '')
                    for em in (rec.get('egrul_emails') or []):
                        db.add_email(inn, em, role='юрзначимый (ЕГРЮЛ)', source='egrul:dadata')
            except Exception:  # noqa: BLE001 — сбой записи одного события не роняет прогон
                pass
        return rec
    except Exception as e:  # noqa: BLE001 — транзиент провайдера/dadata: лог и дальше
        _log(f'извлечение "{item.get("title", "")[:60]}": {type(e).__name__}: {str(e)[:100]}')
        return None


def run(opts, fetch=None):
    """Один прогон «обновить всё». fetch — инжектируемый HTTP (тесты дают фикстуры)."""
    db = EDB.EnrichDB(opts.db)
    SDB.migrate(db)
    lock = threading.Lock()  # одно sqlite-соединение из пула потоков — как в news_scan
    fetcher = no_rss.PoliteFetcher(fetch=fetch, host_pause=opts.pause,
                                   max_pages=opts.max_pages, timeout=opts.timeout)
    donors = SDB.donors_to_poll(db, max_fail=opts.max_fail, limit=opts.max_donors)
    t0 = time.time()
    # «новых сигналов» считаем дельтой таблицы: add_signal — INSERT OR IGNORE,
    # дельта честно не учитывает схлопнутые дубли
    sig_before = db.cx.execute('SELECT COUNT(*) FROM signals').fetchone()[0]
    new_links, errors, donors_ok = 0, 0, 0
    to_extract = []

    # --- фаза 1: опрос доноров (последовательно — вежливость важнее скорости) ---
    for row in donors:
        dom = row['domain']
        try:
            if row['rss']:
                items, err = _poll_rss_donor(fetcher, row, opts.days)
            else:
                items, err = no_rss.poll_donor(db, row, fetcher, opts.days,
                                               max_articles=opts.max_articles)
        except Exception as e:  # noqa: BLE001 — ТРЕБОВАНИЕ: один донор не роняет прогон
            _log(f'донор {dom}: ИСКЛЮЧЕНИЕ {type(e).__name__}: {str(e)[:120]}')
            SDB.donor_fail(db, dom)
            errors += 1
            continue
        if items is None or err == 'fetch':
            _log(f'донор {dom}: недоступен')
            SDB.donor_fail(db, dom)
            errors += 1
            continue
        # дедуп seen_news ДО провайдера: ссылка обрабатывается ОДИН раз за всю жизнь
        # системы (кросс-прогонно) — в этом вся идемпотентность и экономия fable
        fresh_new = []
        for it in items[:opts.max_links]:
            it.setdefault('source', dom)
            it.setdefault('collector', 'cron')
            with lock:
                if db.seen_add(NS._news_key(it)):
                    fresh_new.append(it)
        new_links += len(fresh_new)
        donors_ok += 1
        SDB.donor_ok(db, dom, len(fresh_new))
        if err == 'no-source':
            _log(f'донор {dom}: источник новостей не найден (лестница=none)')
        # капекс-предфильтр заголовка — как в news_scan (не жечь провайдера на мусор)
        to_extract += [it for it in fresh_new if NS._CAPEX_KW.search(it['title'])]

    # --- фаза 2: извлечение сигналов провайдерским API (fable), параллельно ---
    events = []
    if to_extract and not opts.dry_run:
        # ТОЛЬКО fable: haiku на капекс-классификации терял 99% событий
        # (инцидент news_scan, чанк №1) — модель менять лишь осознанно через флаг
        NS.VC._PROVIDER_MODEL = opts.extract_model
        token = os.environ.get('DADATA_TOKEN', '')
        jsonl = None
        if opts.jsonl:
            try:
                jsonl = open(opts.jsonl, 'a', encoding='utf-8')
            except Exception:  # noqa: BLE001
                jsonl = None
        with ThreadPoolExecutor(max_workers=opts.provider_workers) as ex:
            events = [e for e in ex.map(
                lambda it: _extract_one(db, it, token, lock, jsonl), to_extract) if e]
        if jsonl is not None:
            try:
                jsonl.close()
            except Exception:  # noqa: BLE001
                pass

    new_signals = db.cx.execute('SELECT COUNT(*) FROM signals').fetchone()[0] - sig_before
    took = time.time() - t0
    SDB.record_run(db, donors_polled=len(donors), donors_ok=donors_ok,
                   new_links=new_links, new_signals=new_signals, errors=errors,
                   took_sec=took,
                   note=f'capex={len(to_extract)} events={len(events)} dry={int(opts.dry_run)}')
    return {'donors_polled': len(donors), 'donors_ok': donors_ok,
            'new_links': new_links, 'capex_candidates': len(to_extract),
            'events': len(events), 'new_signals': new_signals,
            'errors': errors, 'took_sec': round(took, 1)}


def build_parser():
    p = argparse.ArgumentParser(
        description='Регулярный news-скан: опрос доноров -> сигналы в enrich.db')
    p.add_argument('--db', default=None,
                   help='путь к enrich.db (по умолчанию env ENRICH_DB / C:\\sender\\enrich.db)')
    p.add_argument('--days', type=int, default=30, help='окно свежести новостей, дней')
    p.add_argument('--max-donors', type=int, default=0, help='кап доноров за прогон (0 = все)')
    p.add_argument('--max-links', type=int, default=40,
                   help='кап ссылок с одного донора за прогон (страховка от firehose-лент)')
    p.add_argument('--max-articles', type=int, default=no_rss.MAX_ARTICLES,
                   help='кап страниц-статей на донора (sitemap-путь)')
    p.add_argument('--max-pages', type=int, default=no_rss.MAX_PAGES,
                   help='кап HTTP-запросов на донора')
    p.add_argument('--max-fail', type=int, default=10,
                   help='fail_streak, после которого донора не опрашиваем')
    p.add_argument('--pause', type=float, default=no_rss.HOST_PAUSE,
                   help='пауза между запросами одного хоста, сек (вежливость)')
    p.add_argument('--timeout', type=int, default=no_rss.FETCH_TIMEOUT)
    p.add_argument('--provider-workers', type=int, default=8,
                   help='потоки извлечения (провайдерский API держит параллель)')
    p.add_argument('--extract-model', default='claude-fable-5',
                   help='модель капекс-классификации (haiku тут теряет события — news_scan)')
    p.add_argument('--jsonl', default=os.path.join(_HERE, 'news_stream_cron.jsonl'),
                   help='append-only сток событий (пустая строка = выключить)')
    p.add_argument('--dry-run', action='store_true',
                   help='только опрос/дедуп/метрики, без провайдера и dadata')
    p.add_argument('--report', action='store_true',
                   help='только сводка свежести, без опроса доноров')
    return p


def main(argv=None):
    opts = build_parser().parse_args(argv)
    if opts.report:
        db = EDB.EnrichDB(opts.db)
        SDB.migrate(db)
        print(freshness.report(db))
        return 0
    summary = run(opts)
    print(json.dumps(summary, ensure_ascii=False))
    # свежая сводка после прогона — оператор видит эффект сразу в логе schtasks
    print(freshness.report(EDB.EnrichDB(opts.db)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
