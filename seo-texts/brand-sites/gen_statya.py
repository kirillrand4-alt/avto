#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Статья по готовому ТЗ: текст страницы брендового сайта.

    python3 gen_statya.py --tz tz/TZ-<slug>.md [--out statyi/] [--model ...]
    python3 gen_statya.py --vse            # все ТЗ, у которых ещё нет статьи

ЗАЧЕМ. ТЗ - это бриф копирайтеру, а не текст. Пилот показывает, что
из брифа получается, и ловит те дефекты, которые видны только на готовом
тексте: скучное вступление, повтор одного и того же довода в трёх блоках,
призыв, который не следует из блока.

УСТРОЕН ПО ОБРАЗЦУ ГОСТ-ПОСТОВ (guest-posts/gen_wave.py, волна 2):
черновик - доводки по замечаниям проверок - до трёх раундов. Контракт
ответа НЕ JSON: шлюз на генерационных промптах JSON не отдаёт (замер
03.08 в гост-постах), а длинный простой текст отдаёт. Поэтому первая
строка «TITLE: ...», вторая «DESCRIPTION: ...», дальше голый HTML.

ЧЕМ ОТЛИЧАЕТСЯ ОТ ГОСТ-ПОСТОВОГО. Там тема и стайлгайд, здесь готовое
ТЗ на 40-80 тысяч знаков, и оно СТАРШЕ любых общих соображений: набор
H2 в нём - это разводка, посчитанная на всей сетке из двенадцати сайтов.
Потерянный или переименованный блок ломает не одну страницу, а замер
пересечения по всем. Поэтому совпадение H2 со скелетом ТЗ проверяется
механически и считается браком, а не замечанием.
"""
import argparse, json, os, re, sys, time

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(DIR))
sys.path.insert(0, DIR)
import gen_provider as G
import sanity
import svyaznost

MODELI = ['claude-fable-5', 'claude-opus-4-8']
RAUNDOV = 3
# Норма объёма ЗАВИСИТ ОТ ЧИСЛА БЛОКОВ, а не общая. Кислородная страница
# Atlas Copco с пятнадцатью блоками три раунда ужималась и встала
# на 22 609 знаках: по 1300 знаков на блок плюс вступление, таблицы
# и служебные блоки - в двадцать тысяч это физически не влезает.
# Требовать невозможного значит получить либо обрубленные блоки, либо
# три сожжённых раунда доводки. Считаем от скелета.
OBEM_MIN = 12000
NA_BLOK = 1250                 # знаков на содержательный блок
ZAPAS = 6000                   # вступление, таблицы, служебные блоки, FAQ

# ЯКОРЯ. Решение владельца 21.08. Ставятся на длинных страницах: у нас
# 43 страницы из 131 имеют 13 и больше блоков, это 20-27 тысяч знаков,
# и человек, ищущий цену или подбор, не должен их пролистывать.
#
# ПОЧЕМУ ТРИ ВАРИАНТА, А НЕ ОДИН. Длинные страницы - это станционные,
# и они есть у всех двенадцати доменов. Один и тот же виджет на всех
# дал бы новую общую подпись сетки, а мы весь проект от такой подписи
# и разводимся. Текстового следа блок не добавляет (он собран
# из разведённых H2, общих фраз между сайтами нет), но паттерн разметки
# повторялся бы. Риск невелик - двенадцать доменов одного юрлица и так
# делят хостинг, контакты и CMS, - но развести почти бесплатно, раз
# каждая страница всё равно генерируется отдельно.
#
# СОБИРАЕТСЯ КОДОМ, А НЕ МОДЕЛЬЮ. Модель могла бы переврать заголовок
# в якоре, и тогда проверка скелета поймала бы расхождение там, где
# его нет. Пост-обработка детерминирована.
YAKORYA_OT = int(os.environ.get('YAKORYA_OT', '13'))   # блоков и больше
VARIANT_SAYTA = {
    'abac-kompressor.ru': 'voprosy',
    'berg-kompressor.ru': 'voprosy',
    'enger-air.ru': 'voprosy',
    'ironmac-compressor.com': 'voprosy',
    'ac-kompressor.ru': 'korotkiy',
    'dali-kompressor.ru': 'korotkiy',
    'kraftmann-kompressor.com': 'korotkiy',
    'remeza-kompressor.ru': 'korotkiy',
    'crossair-compressor.ru': 'v_tekste',
    'ekomak-kompressor.com': 'v_tekste',
    'fini-compressor.com': 'v_tekste',
    'zif-kompressor.ru': 'v_tekste',
}
_TR = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z',
       'и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r',
       'с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'c','ч':'ch','ш':'sh',
       'щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'}


def _yakor(zagolovok, n):
    """Читаемый идентификатор из заголовка; при пустом - по номеру."""
    t = ''.join(_TR.get(c, c) for c in zagolovok.lower())
    t = re.sub(r'[^a-z0-9]+', '-', t).strip('-')
    slova = [x for x in t.split('-') if x][:5]
    return '-'.join(slova) or f'blok-{n}'


def _sayt_slug(slug):
    d = {'abac-kompressor': 'abac-kompressor.ru', 'ac-kompressor': 'ac-kompressor.ru',
         'berg-kompressor': 'berg-kompressor.ru',
         'crossair-compressor': 'crossair-compressor.ru',
         'dali-kompressor': 'dali-kompressor.ru',
         'ekomak-kompressor': 'ekomak-kompressor.com', 'enger-air': 'enger-air.ru',
         'fini-compressor': 'fini-compressor.com',
         'ironmac-compressor': 'ironmac-compressor.com',
         'kraftmann-kompressor': 'kraftmann-kompressor.com',
         'remeza-kompressor': 'remeza-kompressor.ru', 'zif-kompressor': 'zif-kompressor.ru'}
    return d.get(slug.split('--')[0], '')


def yakorya(html, slug):
    """Расставить id на H2 и вставить навигацию. Возврат (html, что сделано)."""
    zagolovki = re.findall(r'<h2[^>]*>(.*?)</h2>', html, re.S | re.I)
    chistye = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', z)).strip()
               for z in zagolovki]
    if len(chistye) < YAKORYA_OT:
        return html, f'якорей нет: блоков {len(chistye)}, порог {YAKORYA_OT}'
    variant = VARIANT_SAYTA.get(_sayt_slug(slug), 'voprosy')

    # id на каждый H2, не трогая текст заголовка
    ids, n = [], 0
    def _pometit(m):
        nonlocal n
        n += 1
        txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', m.group(2))).strip()
        i = _yakor(txt, n)
        ids.append((i, txt))
        atr = m.group(1)
        if 'id=' in atr:
            return m.group(0)
        return f'<h2{atr} id="{i}">{m.group(2)}</h2>'
    html = re.sub(r'<h2([^>]*)>(.*?)</h2>', _pometit, html, flags=re.S | re.I)

    if variant == 'korotkiy':
        beru = ids[:4]
        punkty = ' '.join(f'<a href="#{i}">{t}</a>;' for i, t in beru).rstrip(';')
        blok = f'<p class="na-stranice">Что на этой странице: {punkty}.</p>'
    elif variant == 'v_tekste':
        beru = ids[:3]
        punkty = ', '.join(f'<a href="#{i}">{t.lower()}</a>' for i, t in beru)
        blok = (f'<p class="na-stranice">Ниже по порядку: {punkty} '
                f'и остальные разделы.</p>')
    else:
        punkty = '<br>'.join(f'<a href="#{i}">{t}</a>' for i, t in ids)
        blok = f'<p class="na-stranice">{punkty}</p>'

    # ПОСЛЕ первого экрана, а не до: иначе навигация оттеснит вниз две
    # дорожки заявки, ради которых страница и написана.
    m = re.search(r'</p>', html)
    if m:
        html = html[:m.end()] + '\n' + blok + html[m.end():]
    else:
        html = blok + '\n' + html
    return html, f'якоря: {variant}, {len(ids)} блоков'



def razobrat_tz(t):
    """Из ТЗ: H1, Title, Description, список H2 и запрещённые слова."""
    def iz_tablicy(imya):
        m = re.search(rf'\|\s*\**{imya}\**\s*\|\s*([^|\n]+)\|', t, re.I)
        return m.group(1).strip() if m else ''
    h2 = re.findall(r'^###\s*H2:\s*(.+)$', t, re.M)
    zapret = []
    for kus in re.findall(r'^#{2,3}[^\n]*(?:запрет|запрещ|нельзя)[^\n]*\n(.*?)(?=^#{2,3}\s|\Z)',
                          t, re.M | re.S | re.I):
        zapret += [s.strip(' -*') for s in kus.split('\n') if len(s.strip(' -*')) > 10]
    return {'h1': iz_tablicy('H1'), 'title': iz_tablicy('Title'),
            'description': iz_tablicy('Description'), 'h2': h2,
            'zapret': zapret[:40]}


def prompt(tz, sh):
    h2 = '\n'.join(f'   {i + 1}. {x}' for i, x in enumerate(sh['h2']))
    norma = _norma(sh)
    n_blokov = len(sh['h2'])
    return f"""Ты пишешь ТЕКСТ СТРАНИЦЫ каталога промышленного оборудования
по готовому техническому заданию. Заказчик - ООО «Руспром».

Задание ниже - это ЗАКОН. Оно старше твоих общих соображений о предмете
и о том, «как обычно пишут такие страницы».

=== ТЕХНИЧЕСКОЕ ЗАДАНИЕ ===
{tz}
=== КОНЕЦ ЗАДАНИЯ ===

ЧТО ОТ ТЕБЯ НУЖНО.

ЗАГОЛОВКИ H2 - РОВНО ТЕ, ЧТО В ЗАДАНИИ, в этом же порядке, слово в слово:
{h2}

Ни одного не пропустить, ни одного не переименовать, своих не добавлять.
Это не стилистическая придирка: набор блоков посчитан на сетке
из двенадцати сайтов, чтобы страницы не склеились в выдаче. Потерянный
блок ломает замер на всей сетке, а не на одной странице.

ЧИСЛА. Только те, что стоят в задании. Ни одного нового, ни в каком
виде, включая осторожные формы «около», «примерно», «может быть».
Если для мысли не хватает числа - выражай мысль без числа.

ЧЕГО НЕЛЬЗЯ, из самого задания:
{chr(10).join('   - ' + z for z in sh['zapret'][:25])}

ФОРМА:
- длинных тире не ставить вовсе, только короткие;
- списков <ul> и <li> НЕ использовать: вёрстка сайта рисует их иначе,
  чем ты ожидаешь. Перечисление - обычным текстом через точку с запятой;
- разметка простая: <h2>, <p>, <table> где задание требует таблицу;
- байлайн в конце: ООО «Руспром»;
- объём {norma[0]}-{norma[1]} знаков без тегов (посчитано по числу
  блоков скелета: их {n_blokov}).

ЯЗЫК. Пишешь для инженера или закупщика, который решает задачу, а не
для поисковика. Без «широкого ассортимента», «оптимальных решений»,
«надёжных партнёров». Конкретика вместо обещаний: что за машина, из чего
складывается цена, что нужно прислать для расчёта.

ФОРМАТ ОТВЕТА, строго:
TITLE: {sh['title']}
DESCRIPTION: {sh['description']}
<h2>первый заголовок</h2>
<p>...</p>

Первая строка TITLE, вторая DESCRIPTION, дальше сразу HTML тела без
обёрток и без ```. H1 в теле не повторять."""


def razobrat_otvet(raw):
    m = re.match(r'\s*TITLE:\s*(.+?)\n\s*DESCRIPTION:\s*(.+?)\n(.*)', raw, re.S)
    if not m:
        raise ValueError('нет строк TITLE/DESCRIPTION')
    html = m.group(3).strip()
    html = re.sub(r'^```[a-z]*\n|```$', '', html).strip()
    if '<' not in html:
        raise ValueError('тело без HTML-разметки')
    return m.group(1).strip(), m.group(2).strip(), html


def _tekst(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()


def _norma(sh):
    verh = max(20000, len(sh['h2']) * NA_BLOK + ZAPAS)
    return OBEM_MIN, verh


def proverit(html, sh, gazovaya):
    """Претензии к готовому тексту. Пусто - чисто."""
    t = _tekst(html)
    p = []
    nizh, verh = _norma(sh)
    if not (nizh <= len(t) <= verh):
        p.append(f'объём {len(t)} знаков, норма {nizh}-{verh} '
                 f'(по {len(sh["h2"])} блокам скелета)')
    if '—' in html or '–' in html:
        p.append('длинные тире запрещены')
    if '<ul' in html.lower() or '<li' in html.lower():
        p.append('списки ul/li запрещены, вёрстка сайта их ломает')
    # СКЕЛЕТ. Строже прочего: набор H2 - это разводка по всей сетке.
    est = [re.sub(r'\s+', ' ', x).strip().lower()
           for x in re.findall(r'<h2[^>]*>(.*?)</h2>', html, re.S | re.I)]
    est = [re.sub(r'<[^>]+>', '', x) for x in est]
    for nado in sh['h2']:
        n = re.sub(r'\s+', ' ', nado).strip().lower()
        if not any(n[:40] in e or e[:40] in n for e in est):
            p.append(f'потерян блок ТЗ: {nado[:70]}')
    lishnie = len(est) - len(sh['h2'])
    if lishnie > 0:
        p.append(f'лишних H2: {lishnie}, своих блоков добавлять нельзя')
    # смысловые гейты сетки
    v = sanity.vozduh_na_gaz(t)
    if v:
        p.append('выдуманное соотношение воздух/газ: ' + v[0][-90:])
    o = sanity.otechestvennaya_stanciya(t, gazovaya)
    if o:
        p.append('отечественность приписана станции целиком: ' + o[0][-90:])
    for n in svyaznost.pereschety(t) + svyaznost.umnozheniya(t):
        p.append(f"числа не сходятся: {n['в тексте']} -> должно {n['должно быть']}")
    return p


def odna(put, out_dir, model, tries=RAUNDOV):
    slug = os.path.basename(put)[3:-3]
    tz = open(put, encoding='utf-8').read()
    sh = razobrat_tz(tz)
    if not sh['h2']:
        return {'slug': slug, 'chisto': False, 'pretenzii': ['в ТЗ не нашлось ни одного H2']}
    gaz = bool(re.search(r'azotn|kislorod|generatory-(azota|kisloroda)|mks', slug, re.I))
    msgs = [{'role': 'user', 'content': prompt(tz, sh)}]
    t0, html, pret = time.time(), None, ['не сгенерировано']
    for k in range(tries):
        msg = G.call(None, msgs, model=model, attempts=4, max_tokens=32000,
                     thinking_on=False)
        raw = ''.join(b.text for b in msg.content if b.type == 'text').strip()
        try:
            title, desc, html = razobrat_otvet(raw)
        except ValueError as e:
            msgs = msgs[:1] + [{'role': 'user', 'content':
                                f'Формат нарушен ({e}). Повтори СТРОГО: первая строка '
                                'TITLE:, вторая DESCRIPTION:, дальше HTML тела.'}]
            continue
        pret = proverit(html, sh, gaz)
        if not pret:
            break
        print(f'   {slug}: раунд {k + 1}, претензий {len(pret)}: '
              + '; '.join(pret)[:170], file=sys.stderr, flush=True)
        msgs = msgs[:1] + [
            {'role': 'assistant', 'content': raw},
            {'role': 'user', 'content': 'Проверка нашла нарушения:\n- '
             + '\n- '.join(pret) + '\nИсправь ТОЛЬКО это, остальное не трогай. '
             'Верни ПОЛНЫЙ ответ в том же формате, не сокращая текст.'}]
    if html is None:
        return {'slug': slug, 'chisto': False, 'pretenzii': ['формат не отдался']}
    # Якоря ставятся ПОСЛЕ проверок: они не меняют текст заголовков,
    # значит проверка скелета уже отработала на чистом документе.
    html, yak = yakorya(html, slug)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f'{slug}.html'), 'w', encoding='utf-8') as f:
        f.write(f'<h1>{sh["h1"]}</h1>\n{html}\n')
        f.flush(); os.fsync(f.fileno())
    meta = {'slug': slug, 'title': title, 'description': desc,
            'znakov': len(_tekst(html)), 'h2_v_tz': len(sh['h2']),
            'yakorya': yak,
            'chisto': not pret, 'pretenzii': pret,
            'sekund': round(time.time() - t0), 'model': model}
    with open(os.path.join(out_dir, f'{slug}.meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
        f.flush(); os.fsync(f.fileno())
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tz')
    ap.add_argument('--vse', action='store_true')
    ap.add_argument('--out', default=os.path.join(DIR, 'statyi'))
    ap.add_argument('--model', default=MODELI[0])
    a = ap.parse_args()

    if a.vse:
        puti = [os.path.join(DIR, 'tz', n) for n in sorted(os.listdir(os.path.join(DIR, 'tz')))
                if n.endswith('.md')
                and not os.path.exists(os.path.join(a.out, n[3:-3] + '.html'))]
    elif a.tz:
        puti = [a.tz]
    else:
        print('нужен --tz <файл> или --vse', file=sys.stderr)
        return 2

    print(f'статей к прогону: {len(puti)}', flush=True)
    itog = []
    for i, p in enumerate(puti):
        print(f'=== [{i + 1}/{len(puti)}] {os.path.basename(p)}', flush=True)
        try:
            m = odna(p, a.out, a.model)
        except Exception as e:
            m = {'slug': os.path.basename(p)[3:-3], 'chisto': False,
                 'pretenzii': [repr(e)[:160]]}
        itog.append(m)
        print(f"   {m['slug']}: {'ЧИСТО' if m.get('chisto') else 'претензии: ' + '; '.join(m.get('pretenzii', []))[:200]}"
              + (f" | {m.get('znakov')} зн за {m.get('sekund')} с" if m.get('znakov') else ''),
              flush=True)
    chisto = sum(1 for m in itog if m.get('chisto'))
    print(f'\nитог: чисто {chisto} из {len(itog)} -> {a.out}')
    return 0 if chisto == len(itog) else 1


if __name__ == '__main__':
    sys.exit(main())
