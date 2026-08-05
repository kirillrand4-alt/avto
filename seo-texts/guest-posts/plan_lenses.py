#!/usr/bin/env python3
"""Подтверждение месячной раскладки линзами провайдера.

Владелец (05.08.2026): «окончательный выбор и те которые в выбор не попали но были
близки, отправь на подтверждение линзами сео, тематике особо не верь у доноров,
лучше перепроверь глазами с сервера».

Отсюда два принципа:
  * заявленная тематика Miralinks в промпт НЕ передаётся как факт — она идёт
    отдельным полем «что заявлено» и линза обязана её проверить;
  * главный вход линзы — то, что реально увидел browser_probe на площадке
    (donor-eyes-raw.json), а не колонка биржи.

Каждого донора смотрят три линзы на РАЗНЫХ моделях (тематика по факту / релевантность
размещения / SEO-риск), затем судья другой модели сводит вердикт и сравнивает
победителя с близкой альтернативой.

    python3 plan_lenses.py                  # весь план
    python3 plan_lenses.py ftimes.ru        # точечно
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen_provider as gp                                    # noqa: E402
from gen_wave import _openai_stream                          # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN = os.path.join(HERE, 'month-plan.json')
EYES = os.path.join(HERE, 'donor-eyes-raw.json')
OUT = os.path.join(HERE, 'plan-lenses.json')

# разные ИИ на разных линзах — одинаковые модели дают одинаковые слепые пятна
LENS_MODELS = {
    'topic':     'openai:gemini-3.1-pro-preview',
    'relevance': 'claude-fable-5',
    'seorisk':   'openai:gpt-5.6-terra',
}
JUDGE_CHAIN = ['claude-opus-4-8', 'claude-fable-5', 'openai:gemini-3.6-flash']

DECLARED = {
    'kineshemec.ru': 'промышленность Ивановской обл. (текстиль, машиностроение)',
    'samaraonline24.ru': 'промрегион: заводы, нефтехим, автосервисы',
    'operativa.ru': 'AI, автоматизация, «умное производство»',
    'moscow-baku.ru': 'промсотрудничество РФ-Азербайджан, экспортные проекты',
    'new-sebastopol.com': 'судоремонт, стройка, промобъекты',
    'oteplicah.com': 'теплицы, АПК, послеуборочная обработка',
    'ftimes.ru': 'производственная экономика, издержки предприятий',
    'gazetagavrilovka.ru': 'мастерская, ферма, малое производство',
    'krasnodar.bz': 'АПК Кубани, послеуборочная обработка',
    'arh112.ru': 'инвестиции в оборудование, окупаемость переработки',
}


def ask(model: str, prompt: str, tokens: int = 3000, tries: int = 3) -> str:
    last = None
    for a in range(tries):
        if a:
            time.sleep(8 * a)
        try:
            if model.startswith('openai:'):
                text, _ = _openai_stream([{'role': 'user', 'content': prompt}], model[7:], tokens)
            else:
                msg = gp._raw_stream([{'role': 'user', 'content': prompt}], model, tokens,
                                     thinking=False, effort=None)
                text = ''.join(b.text for b in msg.content if b.type == 'text')
            if text.strip():
                return text.strip()
            last = 'пусто'
        except Exception as e:                              # noqa: BLE001
            last = repr(e)[:110]
    return f'[ЛИНЗА НЕ ОТВЕТИЛА: {model}: {last}]'


def eyes_digest(dom: str, eyes: dict) -> str:
    """Компактная выжимка того, что реально увидели на площадке."""
    d = eyes.get(dom)
    if not d:
        return 'СЪЁМ С СЕРВЕРА НЕ ВЫПОЛНЕН — судить о тематике не по чему.'
    parts = []
    for p in d.get('pages', []):
        if (p.get('http_status') or 0) >= 400 or (p.get('html_len') or 0) < 500:
            continue
        blk = [f"URL: {p['url']}  (HTTP {p.get('http_status')})"]
        if p.get('title'):
            blk.append(f"title: {p['title'][:200]}")
        if p.get('description'):
            blk.append(f"description: {p['description'][:200]}")
        if p.get('headings'):
            blk.append('заголовки h1-h3: ' + ' | '.join(p['headings'][:15]))
        if p.get('headlines'):
            blk.append('заголовки материалов: ' + ' | '.join(p['headlines'][:25]))
        if p.get('text_head'):
            blk.append('текст: ' + p['text_head'][:900])
        parts.append('\n'.join(blk))
    if not parts:
        err = d.get('runner_error') or 'страницы пусты/закрыты антиботом'
        return f'СЪЁМ НЕ УДАЛСЯ: {err}. Тематику подтвердить нечем — это само по себе риск.'
    return '\n\n---\n'.join(parts[:5])[:9000]


def links_text(row: dict) -> str:
    core = '\n'.join(
        f"  - №{c['n']} [{'Enger' if c['site'] == 'enger' else 'ProKompressor'}] "
        f"{c['url']} — {c['segment']}"
        + ('' if c['from_matrix'] else '   (ВНЕ матрицы донор-фита владельца, добавлено солвером)')
        for c in row['core'])
    deal = '\n'.join(f"  - дилер {x['url']} — {x['segment']}" for x in row['dealers'])
    return core + ('\n' + deal if deal else '')


P_TOPIC = """Ты - SEO-аналитик, который проверяет площадку ПО ФАКТУ, а не по карточке биржи.

Площадка: {dom}
Что о ней ЗАЯВЛЕНО в выгрузке биржи (это НЕ факт, биржа тематику не верифицирует):
«{declared}»

Ниже - то, что реально сняли с площадки браузером с сервера (главная + разделы):

{eyes}

Задай себе вопросы и ответь по ним коротко и предметно:
1. КАКАЯ ТЕМАТИКА НА САМОМ ДЕЛЕ? Назови 2-4 реальные рубрики, которые видно по
   заголовкам материалов. Если это универсальный новостник «обо всём» - так и скажи.
2. СОВПАДАЕТ ЛИ С ЗАЯВЛЕННЫМ? Ответ: СОВПАДАЕТ / ЧАСТИЧНО / НЕ СОВПАДАЕТ + одна фраза почему.
3. ЕСТЬ ЛИ B2B-ПРОМЫШЛЕННЫЙ СЛОЙ, куда органично ложится статья про компрессоры,
   сжатый воздух, промышленное оборудование? Ответ: ЕСТЬ / СЛАБЫЙ / НЕТ.
4. ПРИЗНАКИ ЛИНКОПОМОЙКИ по увиденному: сплошные рекламные/заказные материалы,
   «на правах рекламы», рерайт-новости пачками, отсутствие своей редакции. Перечисли
   что видно, или напиши «не видно».
5. ЧТО НАСТОРАЖИВАЕТ ещё (пустые разделы, мёртвые даты, капча, дорвейные признаки).

В конце строкой: ФАКТ-ТЕМАТИКА: <2-4 слова> | СОВПАДЕНИЕ: <СОВПАДАЕТ|ЧАСТИЧНО|НЕ СОВПАДАЕТ> | B2B-СЛОЙ: <ЕСТЬ|СЛАБЫЙ|НЕТ>"""

P_RELEVANCE = """Ты - SEO-специалист по внешним ссылкам. Оцени, насколько органично на ЭТУ
площадку ложится статья со ссылками на ЭТИ наши страницы.

Площадка: {dom}
Что реально сняли с площадки браузером (не карточка биржи, а живой снимок):

{eyes}

Мы планируем разместить одну статью со ссылками:
{links}

Оцени по пунктам:
1. МЕСТО РАЗМЕЩЕНИЯ (1-10): найдётся ли на площадке рубрика, где такая статья не будет
   выглядеть инородной. Назови рубрику по факту снимка.
2. РЕЛЕВАНТНОСТЬ ССЫЛОК (1-10): насколько аудитория площадки - реальный покупатель
   именно этих страниц. Разбери КАЖДУЮ ссылку отдельно, коротко.
3. УГОЛ СТАТЬИ: сформулируй один угол, при котором статья читается как материал этой
   площадки, а не как реклама. Если органичного угла нет - так и скажи прямо.
4. ПЕРЕГРУЗ: {n} ссылок в одной статье - нормально или заметно? Если заметно, какую
   ссылку убрать первой.

Порог приёмки: место >= 7 И релевантность >= 7. В конце строкой:
МЕСТО: <N> | РЕЛЕВАНТНОСТЬ: <N> | ВЕРДИКТ: <PASS|FAIL> | УБРАТЬ: <ссылка или «-»>"""

P_SEORISK = """Ты - SEO-аудитор, специализация: риски ссылочного профиля под Яндекс
(Минусинск) и Google (SpamBrain). Смотри придирчиво, ищи повод сказать «нет».

Площадка: {dom}
Снимок площадки с сервера:

{eyes}

План размещения на ней (одна статья):
{links}

Контекст сети: у нас prokompressor.ru (основной), enger-air.ru (сайт производителя)
и 6 дилерских сайтов одной компании (ООО «Руспром»). За месяц идёт 10 статей на 10
разных доноров, всего 21 ссылка, из них на Enger 6 и на ProKompressor 9.

Оцени риски именно этого размещения:
1. АФФИЛИАТ-СЛЕД: если в одной статье стоят ссылки на два наших сайта - насколько это
   палит сеть? Что делать: разнести по разным статьям или оставить?
2. АНКОРЫ: какие типы анкоров безопасны здесь (брендовый / навигационный / разбавленный /
   точный коммерческий)? Сколько точных коммерческих допустимо - и допустимо ли вообще?
3. КАЧЕСТВО ДОНОРА ПО СНИМКУ: тянет ли площадка на «естественную» ссылку или ссылка
   будет выглядеть купленной. Что конкретно её выдаёт.
4. ПРИОРИТЕТ РИСКА: РАЗМЕЩАТЬ / РАЗМЕЩАТЬ С ПРАВКАМИ / НЕ РАЗМЕЩАТЬ, и одной фразой - почему.

В конце строкой: РИСК: <НИЗКИЙ|СРЕДНИЙ|ВЫСОКИЙ> | РЕШЕНИЕ: <РАЗМЕЩАТЬ|С ПРАВКАМИ|НЕ РАЗМЕЩАТЬ>"""

P_JUDGE = """Ты - главный судья по размещению. Перед тобой три независимые линзы по одной
площадке (разные модели) и вопрос: подтвердить выбранную раскладку или взять альтернативу,
которая в переборе была рядом.

Площадка: {dom}
Заявленная биржей тематика (не факт): «{declared}»

ВЫБРАННАЯ РАСКЛАДКА:
{links}

БЛИЖАЙШАЯ АЛЬТЕРНАТИВА (проходит те же жёсткие ограничения, уступила по фит-баллу):
{alt}

ЛИНЗА «ТЕМАТИКА ПО ФАКТУ»:
{topic}

ЛИНЗА «РЕЛЕВАНТНОСТЬ РАЗМЕЩЕНИЯ»:
{relevance}

ЛИНЗА «SEO-РИСК»:
{seorisk}

Реши и обоснуй в 4-6 предложениях. Отдельно ответь: если линзы разошлись - чью оценку
берёшь и почему. Если съём с сервера не удался - это НЕ повод подтверждать вслепую.

В конце строкой:
ИТОГ: <ПОДТВЕРДИТЬ|ВЗЯТЬ АЛЬТЕРНАТИВУ|ОТЛОЖИТЬ ДОНОРА> | УВЕРЕННОСТЬ: <1-10> | ГЛАВНОЕ: <одна фраза>"""


def tail_field(text: str, field: str) -> str:
    m = re.findall(rf'{field}:\s*([^|\n]+)', text or '')
    return m[-1].strip() if m else '?'


def review(dom: str, row: dict, alt_txt: str, eyes: dict) -> dict:
    ed = eyes_digest(dom, eyes)
    lt = links_text(row)
    декл = DECLARED.get(dom, '(нет данных)')

    prompts = {
        'topic': P_TOPIC.format(dom=dom, declared=декл, eyes=ed),
        'relevance': P_RELEVANCE.format(dom=dom, eyes=ed, links=lt, n=row['links']),
        'seorisk': P_SEORISK.format(dom=dom, eyes=ed, links=lt),
    }
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = {k: pool.submit(ask, LENS_MODELS[k], p) for k, p in prompts.items()}
        lens = {k: f.result() for k, f in futs.items()}

    jp = P_JUDGE.format(dom=dom, declared=декл, links=lt, alt=alt_txt or '(альтернатив не было)',
                        topic=lens['topic'], relevance=lens['relevance'], seorisk=lens['seorisk'])
    verdict = ''
    for m in JUDGE_CHAIN:
        verdict = ask(m, jp, 2500, tries=2)
        if not verdict.startswith('[ЛИНЗА НЕ ОТВЕТИЛА'):
            break

    return {
        'donor': dom, 'prio': row['prio'], 'lenses': lens, 'judge': verdict,
        'summary': {
            'факт_тематика': tail_field(lens['topic'], 'ФАКТ-ТЕМАТИКА'),
            'совпадение': tail_field(lens['topic'], 'СОВПАДЕНИЕ'),
            'b2b_слой': tail_field(lens['topic'], 'B2B-СЛОЙ'),
            'место': tail_field(lens['relevance'], 'МЕСТО'),
            'релевантность': tail_field(lens['relevance'], 'РЕЛЕВАНТНОСТЬ'),
            'вердикт_релевантности': tail_field(lens['relevance'], 'ВЕРДИКТ'),
            'риск': tail_field(lens['seorisk'], 'РИСК'),
            'решение_риска': tail_field(lens['seorisk'], 'РЕШЕНИЕ'),
            'итог': tail_field(verdict, 'ИТОГ'),
            'уверенность': tail_field(verdict, 'УВЕРЕННОСТЬ'),
            'главное': tail_field(verdict, 'ГЛАВНОЕ'),
        },
    }


def alt_for(dom: str, plan: dict) -> str:
    """Ближайшая альтернатива именно по этому донору (из перебора)."""
    for a in plan.get('alternatives', []):
        for d in a['diff']:
            if d['donor'] == dom:
                core = ', '.join(f'№{n} ({ACC[n]})' for n in d['alt']['core'])
                deal = ', '.join(d['alt']['dealers'])
                return (f"фит {a['score']} ({a['delta']:+}): {core}"
                        + (f" + дилеры {deal}" if deal else ''))
    return ''


ACC = {}


def main() -> int:
    only = sys.argv[1:]
    plan = json.load(open(PLAN, encoding='utf-8'))
    eyes = json.load(open(EYES, encoding='utf-8')) if os.path.exists(EYES) else {}
    if not eyes:
        print('ВНИМАНИЕ: donor-eyes-raw.json нет — линзы будут судить вслепую.', file=sys.stderr)

    for a, u in plan['acceptor_usage'].items():
        pass
    for r in plan['rows']:
        for c in r['core']:
            ACC[c['n']] = c['segment']

    rows = [r for r in plan['rows'] if not only or r['donor'] in only]
    print(f'линзы по {len(rows)} донорам '
          f'(тематика={LENS_MODELS["topic"]}, релевантность={LENS_MODELS["relevance"]}, '
          f'риск={LENS_MODELS["seorisk"]}, судья={JUDGE_CHAIN[0]})\n')

    out = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = [pool.submit(review, r['donor'], r, alt_for(r['donor'], plan), eyes) for r in rows]
        for f in futs:
            res = f.result()
            out.append(res)
            s = res['summary']
            print(f"{res['prio']:>2}. {res['donor']:<22} факт: {s['факт_тематика'][:28]:<28} "
                  f"совп: {s['совпадение']:<14} b2b: {s['b2b_слой']:<8} "
                  f"место/релев: {s['место']}/{s['релевантность']:<4} риск: {s['риск']:<9} "
                  f"итог: {s['итог']}")

    out.sort(key=lambda x: x['prio'])
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f'\n-> {OUT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
