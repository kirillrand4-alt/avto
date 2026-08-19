#!/usr/bin/env python3
"""Планировщик джоб: агент на каждого донора выбирает акцептор, угол и анкоры.

Один прогон = один донор. Агент видит: чем площадка живёт по РЕАЛЬНЫМ поисковым
запросам (не по колонке биржи), её лимиты из карточки, закреплённый за ней наш сайт
и все его страницы из плана v15 с деньгами, позициями, готовыми анкорами и живыми
инфо-запросами. Возвращает заполненную джобу для `gen_wave.py` плюс обоснование.

Почему через провайдерский API, а не подагентами сессии: правило владельца - вся
тяжёлая работа идёт через оплаченный шлюз, квота сессии только на оркестрацию.

Контракт ответа - plain-text блоками «КЛЮЧ: значение»: шлюз не отдаёт длинные JSON
(README §4.10), на этом уже спотыкались генератор и линзы.

    python3 plan_jobs.py [донор ...]      # без аргументов - все из раскладки
"""
from __future__ import annotations

import concurrent.futures as cf
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen_provider as gp                                    # noqa: E402

OUT = os.environ.get('JOBS_OUT', 'planned-jobs.jsonl')


def decisions():
    """Решения владельца. Идут первым блоком промпта и стоят ВЫШЕ таблиц.

    Правило владельца 19.08: «мне надо чтобы то что обсуждали в первую очередь
    попадало в статьи, а то что в таблице написано - таблица вторична». Прогнозы
    дохода и позиции - вход для расчёта, а не закон: ветка станций с нулём в плане
    важнее строки с 10 000 ₽, если владелец отобрал её руками.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'OWNER-DECISIONS.md')
    return open(path, encoding='utf-8').read().strip()

# Раскладка донор -> наш сайт (решение владельца 19.08: качаем основной + сателлиты,
# enger-air.ru в этой волне не первый). Один донор - один наш сайт, навсегда.
ASSIGN = {
    # prokompressor.ru - основной
    'metallicheckiy-portal.ru': 'prokompressor.ru', 'perekos.net': 'prokompressor.ru',
    'flotenk.ru': 'prokompressor.ru', 'citaty.info': 'prokompressor.ru',
    'berkat.ru': 'prokompressor.ru', 'get-color.ru': 'prokompressor.ru',
    'kakoj-segodnja-prazdnik.com': 'prokompressor.ru', '4tololo.ru': 'prokompressor.ru',
    'tvcenter.ru': 'prokompressor.ru', 'twizz.ru': 'prokompressor.ru',
    'factories.kz': 'prokompressor.ru', 'satom.ru': 'prokompressor.ru',
    # сателлиты
    'topclimat.ru': 'berg-compressor.com', 'ess-ltd.ru': 'berg-compressor.com',
    'afk-arena.com': 'berg-compressor.com',
    'koch-market.ru': 'dali-kompressor.ru', 'galan.ru': 'dali-kompressor.ru',
    'mplast.by': 'abac-kompressor.ru', 'lada-granta.ru': 'abac-kompressor.ru',
    'truckmix.ru': 'ac-kompressor.ru', 'fgisrf.ru': 'ac-kompressor.ru',
    # enger-air.ru - остаток
    'nashaplaneta.net': 'enger-air.ru', 'moluch.ru': 'enger-air.ru',
    'gorod24.online': 'enger-air.ru',
}

GENRE = {
    'citaty.info': 'цитаты из фильмов и аниме, мотивационные подборки',
    'berkat.ru': 'доска объявлений Ингушетии: работа, аренда жилья',
    'get-color.ru': 'цвет и палитры, онлайн-инструменты дизайнера',
    'kakoj-segodnja-prazdnik.com': 'календарь праздников и памятных дат',
    '4tololo.ru': 'развлекательный контент, необычное и аномалии',
    'tvcenter.ru': 'шоу-бизнес и знаменитости',
    'twizz.ru': 'мемы и интернет-фольклор',
    'afk-arena.com': 'компьютерные игры, гайды и коды',
    'nashaplaneta.net': 'туризм: курорты, пляжи, погода',
    'moluch.ru': 'научно-образовательный, студенческий',
    'gorod24.online': 'новости Крыма',
    'satom.ru': 'дача и частное хозяйство, товары для дома',
}

PROMPT = """=== РЕШЕНИЯ ВЛАДЕЛЬЦА (приоритет выше любых таблиц и прогнозов) ===
{decisions}

=== ЗАДАЧА ===
Ты планируешь гостевую статью для поставщика промышленного компрессорного
оборудования (ООО «Руспром»): винтовые и поршневые компрессоры, компрессорные станции,
генераторы азота и кислорода, осушители сжатого воздуха, ресиверы.

Статью ты НЕ пишешь. Ты решаешь: на какую нашу страницу вести ссылку, о чём будет
статья, каким якорем встанет ссылка и в каком жанре текст должен быть написан.

=== ПЛОЩАДКА-ДОНОР ===
{donor_block}

=== НАШ САЙТ, ЗА КОТОРЫМ ЗАКРЕПЛЁН ЭТОТ ДОНОР: {site} ===
Ссылки ведут ТОЛЬКО на этот сайт. Ставить ссылки на два наших сайта в одной статье
запрещено. Страницы на выбор (деньги = прогноз дохода от прироста позиций, ₽/мес):

{pages_block}

=== ПРАВИЛА ===
1. Лимит ссылок в статье у этой площадки: {max_links}. Лимит наших доменов: {max_domains}.
   Больше не ставить. Если лимит 2-3 - можно категория + подкатегория ОДНОГО сайта,
   но только если это осмысленно, а не «чтобы занять слот».
2. Тип якоря. {anchor_rule}
   Имя бренда допустимо ТОЛЬКО внутри текста якоря, в остальном тексте брендов и
   названий наших компаний нет.
3. Тему не натягивать. Если пересечение предмета страницы с аудиторией площадки пустое -
   так и напиши в ВЕРДИКТ: отказ, и объясни. Это нормальный исход, а не провал.
4. Кейс в статье обезличенный: без юрлиц клиентов, без брендов, без артикулов.
5. Никаких чисел и фактов, которых нет во входных данных. Выдуманные местные факты
   («в нашем городе на заводе N») запрещены.
6. Жанр: {genre_rule}

=== ФОРМАТ ОТВЕТА (строго, plain text, без markdown и без JSON) ===
ВЕРДИКТ: годен | отказ
SLUG: короткий-слаг-латиницей
СТРАНИЦА: полный URL нашей страницы
ЯКОРЬ: точный текст якоря
СТРАНИЦА2: полный URL или «нет»
ЯКОРЬ2: текст якоря или «нет»
УГОЛ: 2-4 предложения - о чём статья, с инженерной конкретикой
КЕЙС: одно предложение, обезличенно
СКЕЛЕТ: постановка задачи -> разбор -> подбор -> резюме (своими словами под тему)
ЗАМЕТКА О ПЛОЩАДКЕ: кто читает и как с ними говорить
SEO: главный ключ + 3-5 живых запросов через точку с запятой + LSI-термины
ПОЧЕМУ: 3-4 строки - почему эта страница (деньги, позиция), почему такой угол
        (какое пересечение), какие лимиты площадки учтены
"""


def load():
    cards = {r['domain']: r for r in json.load(open('ml-cards.json', encoding='utf-8'))}
    v15 = json.load(open('acceptors-v15.json', encoding='utf-8'))
    pq = {(r['site'], r['page']): r for r in json.load(open('plan-queries.json', encoding='utf-8'))}
    sem = {r['domain']: r for r in json.load(open('weight-verdicts.json', encoding='utf-8'))}
    th = {r['dom']: r for r in json.load(open('THEMATIC-FINAL.json', encoding='utf-8'))}
    return cards, v15, pq, sem, th


def pages_for(site, v15, pq, limit=8):
    # Страницы с нулевым прогнозом отбрасывать нельзя: ветка станций prokompressor.ru
    # появилась в июле 2026, денег ещё не набрала, но помечена ручным приоритетом
    # владельца - и модульные станции есть именно там.
    rows = [r for r in v15 if r['site'] == site
            and ((r['money'] or 0) > 0 or r.get('manual'))]
    rows.sort(key=lambda r: -(float(r['money'] or 0)))
    if not rows:                                             # ac-kompressor: денег нет, но качаем
        rows = [r for r in v15 if r['site'] == site]
    out = []
    for r in rows[:limit]:
        q = pq.get((site, r['page']), {})
        anc = [a for a in (r['anchors'] or {}).values() if a]
        # Кандидаты в якорь из выгрузки Search Console: это ФРАЗЫ, которые реально
        # набирают показы, а шесть слотов v15 - синтез из адреса страницы. Живой
        # вариант с 4834 показами точнее придуманного, поэтому даём и то, и другое.
        cand = '; '.join('%s (%s показов, поз. %s)' % (a['q'], a['imp90'], a['pos'])
                         for a in (q.get('anchors') or [])[:6] if a.get('q'))
        themes = '; '.join(t['theme'] for t in (q.get('themes') or [])[:4] if t['theme'])
        words = ', '.join(w['w'] for w in (q.get('words') or [])[:10] if w['w'])
        block = f"* https://{site}{r['page']}\n"
        if r.get('manual'):
            block += f"  РУЧНОЙ ПРИОРИТЕТ ВЛАДЕЛЬЦА: {r['manual']}\n"
        block += (f"  деньги {int(float(r['money'] or 0))} ₽/мес | "
                  f"позиция Google {r['pos_google']} | тренд {r['trend']} | "
                  f"надёжность {r['reliability']}")
        if r['warning']:
            block += f" | ВНИМАНИЕ: {r['warning']}"
        block += f"\n  готовые анкоры (слоты плана): {' | '.join(anc)}\n"
        if cand:
            block += f"  живые запросы-кандидаты в якорь: {cand}\n"
        if themes:
            block += f"  живые инфо-запросы (годятся как тема статьи): {themes}\n"
        if words:
            block += f"  слова для тела: {words}\n"
        out.append(block)
    return '\n'.join(out)


def donor_block(dom, cards, sem, th):
    c = cards.get(dom, {})
    lines = [f'домен: {dom}']
    if dom in th:
        t = th[dom]
        lines += [f"тип: ТЕМАТИЧЕСКАЯ площадка (блок A). Органика {t['tr']}, ИКС {t['iks']}.",
                  f"угол по нашему разбору: {t['angle']}",
                  'аудитория решает производственную задачу - пишем отраслевой разбор.']
    else:
        s = sem.get(dom, {})
        lines += [f"тип: ВЕСОВАЯ площадка (блоки B/C). Наша доля аудитории: {s.get('share', '0-1%')}.",
                  f"чем живёт по реальным запросам: {s.get('why', '')}",
                  f"жанр площадки: {GENRE.get(dom, '')}"]
    lines += [f"лимиты карточки биржи: ссылок в статье {c.get('max_links', '?')}, "
              f"наших доменов {c.get('max_domains', '?')}, "
              f"нетематические ссылки: {c.get('netematic', '?')}, "
              f"вложенность статей {c.get('depth', '?')}, статейность {c.get('statejnost', '?')}"]
    return '\n'.join(lines)


def build(dom, cards, v15, pq, sem, th):
    site = ASSIGN[dom]
    c = cards.get(dom, {})
    thematic = dom in th
    anchor_rule = (
        'Площадка тематическая - бери КОММЕРЧЕСКИЙ или ТОЧНЫЙ анкор из готовых '
        '(«купить …», «… компрессоры БРЕНД»): там они естественны.'
        if thematic else
        'Площадка НЕтематическая - бери только БРЕНДОВЫЙ («ENGER») или БЕЗАНКОРНЫЙ '
        '(домен) вариант. Коммерческий анкор редактор такой площадки завернёт.')
    genre_rule = (
        'отраслевой инженерно-деловой разбор с цифровой конкретикой.'
        if thematic else
        f'статья пишется В ЖАНРЕ ПЛОЩАДКИ ({GENRE.get(dom, "")}), а не как отраслевая '
        'инструкция. Мост к нашей теме должен быть честным: найди задачу, которая '
        'понятна читателю ЭТОЙ площадки и в которой сжатый воздух или газы реально '
        'участвуют. Натянутый мост хуже отказа.')
    return PROMPT.format(
        decisions=decisions(),
        donor_block=donor_block(dom, cards, sem, th), site=site,
        pages_block=pages_for(site, v15, pq),
        max_links=c.get('max_links', '2'), max_domains=c.get('max_domains', '1'),
        anchor_rule=anchor_rule, genre_rule=genre_rule)


def parse(out):
    out = out.replace('*', '')
    g = lambda k: (re.search(rf'^{k}:\s*(.+?)(?=\n[А-ЯA-Z][А-ЯA-Z2 ]{{2,}}:|\Z)', out,
                             re.S | re.M) or [None, ''])[1].strip()
    return {k: g(p) for k, p in [
        ('verdict', 'ВЕРДИКТ'), ('slug', 'SLUG'), ('url', 'СТРАНИЦА'), ('anchor', 'ЯКОРЬ'),
        ('url2', 'СТРАНИЦА2'), ('anchor2', 'ЯКОРЬ2'), ('angle', 'УГОЛ'), ('case', 'КЕЙС'),
        ('skeleton', 'СКЕЛЕТ'), ('donor_note', 'ЗАМЕТКА О ПЛОЩАДКЕ'), ('seo', 'SEO'),
        ('why', 'ПОЧЕМУ')]}


def one(args):
    dom, prompt = args
    try:
        msg = gp.call(None, [{'role': 'user', 'content': prompt}],
                      model='claude-fable-5', attempts=4)
        raw = ''.join(b.text for b in msg.content if b.type == 'text').strip()
    except Exception as e:                                   # noqa: BLE001
        return {'donor': dom, 'error': repr(e)[:150]}
    rec = {'donor': dom, 'site': ASSIGN[dom], **parse(raw), 'raw': raw}
    rec['verdict'] = (rec.get('verdict') or '?').split()[0].lower()
    return rec


def main():
    cards, v15, pq, sem, th = load()
    doms = sys.argv[1:] or list(ASSIGN)
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT, encoding='utf-8'):
            if line.strip():
                r = json.loads(line)
                if not r.get('error'):
                    done.add(r['donor'])
    todo = [d for d in doms if d not in done]
    print(f'доноров: {len(doms)} | готово: {len(done)} | к планированию: {len(todo)}', flush=True)
    tasks = [(d, build(d, cards, v15, pq, sem, th)) for d in todo]
    f = open(OUT, 'a', encoding='utf-8')
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for rec in ex.map(one, tasks):
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush(); os.fsync(f.fileno())
            print('  %-28s %-8s %-26s %s' % (
                rec['donor'], rec.get('verdict', 'ERR'), (rec.get('slug') or '')[:26],
                (rec.get('url') or rec.get('error') or '')[:56]), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
