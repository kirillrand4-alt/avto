#!/usr/bin/env python3
"""Фаза 4: финальные джобы под назначенные страницы.

Углы, придуманные в `plan_jobs.py` и `genre_jobs.py`, рождались до раскладки по
страницам (`dispatch_pages.py`) — а страницы поменялись: metallicheckiy-portal.ru
планировался под лазерную резку, а ведёт на азотные станции. Здесь агент получает
УЖЕ НАЗНАЧЕННУЮ страницу с её живыми запросами и собирает статью под неё.

Две ветки промпта. Тематическая — отраслевой разбор для аудитории, которая решает
производственную задачу. Жанровая — статья по законам площадки, где наша тема
появляется органично, а ссылка стоит справкой; для неё тема уже придумана в
`genre-jobs.jsonl` и передаётся как заданная.

Выход: `final-jobs.jsonl` + `JOBS.py` в формате `gen_wave.JOBS`.

    python3 final_jobs.py [донор ...]
"""
from __future__ import annotations

import concurrent.futures as cf
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen_provider as gp                                    # noqa: E402
from plan_jobs import GENRE, decisions, load, parse          # noqa: E402

OUT = os.environ.get('FINAL_OUT', 'final-jobs.jsonl')

COMMON = """=== РЕШЕНИЯ ВЛАДЕЛЬЦА (приоритет выше любых таблиц) ===
{decisions}

=== ПЛОЩАДКА-ДОНОР ===
домен: {donor}
{donor_info}
лимиты карточки биржи: ссылок в статье {max_links}, наших доменов {max_domains},
нетематические ссылки: {netematic}, вложенность статей {depth}

=== ССЫЛКА (назначена, менять НЕЛЬЗЯ) ===
страница: {url}
якорь: {anchor}
почему эта страница: {why}

Данные страницы:
{page_info}
"""

THEMATIC = COMMON + """
=== ЗАДАЧА ===
Собери задание на статью — отраслевой разбор для аудитории этой площадки, которая
решает производственную задачу. Статью писать не нужно, нужно задание для генератора.

Требования к статье, которые ты закладываешь в задание:
* спокойный инженерно-деловой тон с цифровой конкретикой, без рекламы и призывов;
* кейс обезличенный: без юрлиц клиентов, без брендов, без артикулов;
* структура «постановка задачи -> разбор -> подбор -> практическое резюме»;
  сцены-репортажи и «звонки читателей» запрещены;
* никаких чисел и фактов, которых нет во входных данных — инженерную правду будут
  проверять отдельные линзы, выдуманное они поймают;
* имя бренда допустимо ТОЛЬКО внутри текста якоря, в остальном тексте брендов
  и названий наших компаний нет.

{fmt}
"""

GENRE_P = COMMON + """
=== ЗАДАЧА ===
Тема статьи уже придумана и утверждена:

    {title}

Площадка НЕ про промышленность, и это нормально: статья живёт по законам площадки,
а ссылка стоит внутри как справка на источник — одна, в содержательном месте, не в
лиде и не в подвале. Материал должен быть интересен читателю площадки и без ссылки.

Собери задание на эту статью. Требования:
* жанр и тон — как у площадки ({genre}), а не как у отраслевой инструкции;
* промышленная часть — органичная часть темы, а не её содержание; статья, где 80%
  про компрессоры с декоративным вступлением, не годится;
* без рекламных подводок, призывов и оценок вроде «ведущий поставщик»;
* без выдуманных фактов, чисел и местных подробностей;
* якорь уже назначен, менять нельзя.

{fmt}
"""

FMT = """=== ФОРМАТ ОТВЕТА (строго, plain text, без markdown и JSON) ===
SLUG: короткий-слаг-латиницей
УГОЛ: 3-5 предложений — о чём статья, с конкретикой; для жанровой — где именно
      появляется промышленная часть
КЕЙС: одно предложение, обезличенно, или «не нужен»
СКЕЛЕТ: структура статьи, разделы через ->
ЗАМЕТКА О ПЛОЩАДКЕ: кто читает и как с ними говорить, чего избегать
SEO: главный ключ + 3-5 живых запросов через точку с запятой + LSI-термины
ЗАГОЛОВОК: рабочий заголовок статьи"""


def page_info(site, page, v15, pq):
    key = page.replace(f'https://{site}', '').rstrip('/')
    row = next((r for r in v15 if r['site'] == site and r['page'].rstrip('/') == key), None)
    if not row:
        return 'данных по странице нет'
    q = pq.get((site, row['page']), {})
    out = []
    if row.get('manual'):
        out.append(f"РУЧНОЙ ПРИОРИТЕТ ВЛАДЕЛЬЦА: {row['manual']}")
    out.append(f"деньги {int(float(row['money'] or 0))} ₽/мес | позиция Google "
               f"{row['pos_google']} | тренд {row['trend']} | надёжность {row['reliability']}")
    if row.get('warning'):
        out.append(f"ВНИМАНИЕ: {row['warning']}")
    themes = '; '.join(t['theme'] for t in (q.get('themes') or [])[:5] if t['theme'])
    words = ', '.join(w['w'] for w in (q.get('words') or [])[:14] if w['w'])
    if themes:
        out.append(f"живые инфо-запросы (годятся как тема раздела): {themes}")
    if words:
        out.append(f"слова для тела статьи: {words}")
    return '\n'.join(out)


def build(rec, cards, v15, pq, sem, th, genre_titles):
    dom = rec['donor']
    c = cards.get(dom, {})
    site = rec['url'].replace('https://', '').split('/')[0]
    if dom in th:
        t = th[dom]
        info = (f"тип: тематическая площадка. Органика {t['tr']}, ИКС {t['iks']}.\n"
                f"угол по нашему разбору: {t['angle']}")
    else:
        s = sem.get(dom, {})
        info = (f"тип: площадка без прямой связи с нашей темой. Наша доля аудитории "
                f"{s.get('share', '0-1%')}.\nчем живёт по реальным запросам: {s.get('why', '')}")
    common = dict(decisions=decisions(), donor=dom, donor_info=info,
                  max_links=c.get('max_links', '1'), max_domains=c.get('max_domains', '1'),
                  netematic=c.get('netematic', '?'), depth=c.get('depth', '?'),
                  url=rec['url'], anchor=rec['anchor'], why=rec.get('why', ''),
                  page_info=page_info(site, rec['url'], v15, pq), fmt=FMT)
    if rec['mode'] == 'жанровый':
        return GENRE_P.format(title=genre_titles.get(dom, ''), genre=GENRE.get(dom, ''), **common)
    return THEMATIC.format(**common)


def one(args):
    rec, prompt = args
    try:
        msg = gp.call(None, [{'role': 'user', 'content': prompt}],
                      model='claude-fable-5', attempts=4)
        raw = ''.join(b.text for b in msg.content if b.type == 'text').strip()
    except Exception as e:                                   # noqa: BLE001
        return {'donor': rec['donor'], 'error': repr(e)[:150]}
    import re
    g = lambda k: (re.search(rf'^{k}:\s*(.+?)(?=\n[А-ЯA-Z][А-ЯA-Z ]{{2,}}:|\Z)',
                             raw.replace('*', ''), re.S | re.M) or [None, ''])[1].strip()
    return {'donor': rec['donor'], 'mode': rec['mode'], 'url': rec['url'],
            'anchor': rec['anchor'], 'slug': g('SLUG'), 'angle': g('УГОЛ'), 'case': g('КЕЙС'),
            'skeleton': g('СКЕЛЕТ'), 'donor_note': g('ЗАМЕТКА О ПЛОЩАДКЕ'), 'seo': g('SEO'),
            'title': g('ЗАГОЛОВОК'), 'raw': raw}


def main():
    cards, v15, pq, sem, th = load()
    disp = json.load(open('dispatch.json', encoding='utf-8'))
    genre_titles = {}
    for line in open('genre-jobs.jsonl', encoding='utf-8'):
        if line.strip():
            r = json.loads(line)
            if r.get('title'):
                genre_titles[r['donor']] = r['title']
    want = set(sys.argv[1:])
    recs = [r for r in disp if not want or r['donor'] in want]
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT, encoding='utf-8'):
            if line.strip():
                r = json.loads(line)
                if not r.get('error'):
                    done.add(r['donor'])
    todo = [r for r in recs if r['donor'] not in done]
    print(f'пар: {len(recs)} | готово: {len(done)} | к сборке: {len(todo)}', flush=True)
    tasks = [(r, build(r, cards, v15, pq, sem, th, genre_titles)) for r in todo]
    f = open(OUT, 'a', encoding='utf-8')
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for rec in ex.map(one, tasks):
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush(); os.fsync(f.fileno())
            print('  %-28s %-11s %-26s %s' % (
                rec['donor'], rec.get('mode', ''), (rec.get('slug') or '')[:26],
                (rec.get('title') or rec.get('error') or '')[:56]), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
