# -*- coding: utf-8 -*-
"""Метрики свежести сигналов и здоровья доноров (задача #49-б, п.3).

ЗАЧЕМ: исходная боль — «сигналов моложе 30 дней только 77 из 861», и этого никто
не видел, пока не посчитали руками. Здесь те же цифры считаются НА КАЖДОМ прогоне
и отдаются короткой текстовой сводкой: её печатает news_cron в конце, её же можно
получить отдельно (python news_cron.py --report) без опроса доноров.

Свежесть сигналов меряем по signals.updated_at — момент ЗАПИСИ в БД, надёжное
ISO-поле единого формата (EnrichDB.now). Поле signals.ts — сырой pubDate источника,
форматы вразнобой (RFC2822/ISO/пусто), для SQL-метрики непригодно."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import schedule_db as SDB

SILENT_DAYS = 30   # «молчащий» донор: нет новых ссылок дольше этого
DEAD_STREAK = 5    # «мёртвый» донор: столько ошибок доступности подряд


def metrics(db, silent_days=SILENT_DAYS, dead_streak=DEAD_STREAK):
    """Числа для сводки/панели. Требует schedule_db.migrate(db) — колонки
    last_new/fail_streak появляются миграцией."""
    c = db.cx.execute
    cutoff_silent = SDB.iso_ago(silent_days)
    # «молчащий» = донора опрашиваем (не мёртвый), но НОВЫХ ссылок он не давал
    # дольше silent_days ЛИБО ещё ни разу (last_new пуст — cron его пока не кормил)
    silent = c(
        'SELECT COUNT(*) FROM donors WHERE COALESCE(fail_streak,0)<? '
        "AND (last_new IS NULL OR last_new='' OR last_new<?)",
        (dead_streak, cutoff_silent)).fetchone()[0]
    runs = c('SELECT ts, donors_polled, new_links, new_signals, errors '
             'FROM scan_runs ORDER BY ts DESC LIMIT 5').fetchall()
    return {
        'signals_total': c('SELECT COUNT(*) FROM signals').fetchone()[0],
        'signals_7d': c('SELECT COUNT(*) FROM signals WHERE updated_at>=?',
                        (SDB.iso_ago(7),)).fetchone()[0],
        'signals_30d': c('SELECT COUNT(*) FROM signals WHERE updated_at>=?',
                         (SDB.iso_ago(30),)).fetchone()[0],
        'donors_total': c('SELECT COUNT(*) FROM donors').fetchone()[0],
        'donors_rss': c("SELECT COUNT(*) FROM donors WHERE rss IS NOT NULL AND rss!=''")
                      .fetchone()[0],
        'donors_probe': c("SELECT COUNT(*) FROM donors WHERE (rss IS NULL OR rss='') "
                          "AND probe_method IN ('rss-path','sitemap','listing')")
                        .fetchone()[0],
        'donors_silent': silent,
        'donors_dead': c('SELECT COUNT(*) FROM donors WHERE COALESCE(fail_streak,0)>=?',
                         (dead_streak,)).fetchone()[0],
        'last_runs': [{'ts': r[0], 'donors_polled': r[1], 'new_links': r[2],
                       'new_signals': r[3], 'errors': r[4]} for r in runs],
    }


def report(db, silent_days=SILENT_DAYS, dead_streak=DEAD_STREAK):
    """Краткая сводка текстом (требование задачи): stdout прогона / оператору."""
    m = metrics(db, silent_days, dead_streak)
    lines = [
        'NEWS-СКАН: сводка свежести',
        f"  сигналы: всего {m['signals_total']}, свежее 7д: {m['signals_7d']}, "
        f"свежее 30д: {m['signals_30d']}",
        f"  доноры: всего {m['donors_total']}; с RSS: {m['donors_rss']}; "
        f"без RSS с рабочим способом: {m['donors_probe']}",
        f"  молчащие (>{silent_days}д без новых ссылок): {m['donors_silent']}; "
        f"мёртвые ({dead_streak}+ ошибок подряд): {m['donors_dead']}",
    ]
    if m['last_runs']:
        r = m['last_runs'][0]
        lines.append(f"  последний прогон {r['ts']}: доноров {r['donors_polled']}, "
                     f"новых ссылок {r['new_links']}, новых сигналов {r['new_signals']}, "
                     f"ошибок {r['errors']}")
    else:
        lines.append('  прогонов ещё не было (scan_runs пуст)')
    return '\n'.join(lines)
