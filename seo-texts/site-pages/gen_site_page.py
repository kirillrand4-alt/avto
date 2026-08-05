#!/usr/bin/env python3
"""Генерация коммерческих страниц каталога prokompressor.ru по ТЗ владельца.

    PROVIDER_FIRST_TOKEN_SEC=300 python3 gen_site_page.py [slug ...]
    python3 gen_site_page.py --pack          # только собрать архивы из готовых html

Отличие от гост-постов: качество выше, объём больше, вёрстка сразу боевая (сайтовые
классы из эталонной страницы дожимных станций), картинки и кейсы - из базы знаний.

Генерируем ПОСЕКЦИОННО, а не одним ответом. Причины две:
  * шлюз на длинных генерационных промптах уходит в thinking и отдаёт пустой text
    (проверено на волне 1 гост-постов: ~9k thinking, text 0, end_turn);
  * секция с конкретной задачей и своим списком запретов выходит заметно точнее,
    чем секция внутри полотна на 9000 знаков.
Сборщик потом склеивает секции в готовую разметку и раскладывает картинки и CTA.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import gen_provider as gp                                    # noqa: E402
from pages_spec import PAGES, COMMON_RULES, STYLE_RULES, HTML_RULES   # noqa: E402

MODELS = ['claude-opus-4-8', 'openai:gemini-3.1-pro-preview', 'openai:gemini-3.6-flash']
MAX_TOKENS = int(os.environ.get('SP_MAX_TOKENS', '8000'))
KB = os.path.join(HERE, 'kb-cases.json')
OUT = HERE


def _openai_stream(messages, model, max_tokens):
    """Openai-роут шлюза: нужен для gemini/gpt-моделей."""
    from gen_wave import _openai_stream as f       # noqa: PLC0415
    return f(messages, model, max_tokens)


def ask(prompt: str, tokens: int = MAX_TOKENS, tries: int = 2) -> tuple:
    last = None
    for model in MODELS:
        for a in range(tries):
            if a:
                time.sleep(10)
            try:
                if model.startswith('openai:'):
                    sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'guest-posts'))
                    text, _ = _openai_stream([{'role': 'user', 'content': prompt}],
                                             model[7:], tokens)
                else:
                    msg = gp._raw_stream([{'role': 'user', 'content': prompt}], model, tokens,
                                         thinking=False, effort=None)
                    text = ''.join(b.text for b in msg.content if b.type == 'text')
                if text and len(text.strip()) > 200:
                    return text.strip(), model
                last = f'{model}: коротко/пусто'
            except Exception as e:                          # noqa: BLE001
                last = f'{model}: {repr(e)[:90]}'
    raise RuntimeError(f'секция не сгенерирована: {last}')


def load_cases() -> list:
    if not os.path.exists(KB):
        return []
    return json.load(open(KB, encoding='utf-8'))


def cases_for(slug: str, cases: list, n: int = 3) -> str:
    """Кейсы под тему страницы. Берём только то, что реально есть в базе."""
    gas = 'азот' if 'azot' in slug and 'kislorod' not in slug else (
        'кислород' if 'kislorod' in slug and 'azot' not in slug else 'азот|кислород')
    rx = re.compile(gas, re.I)
    hits = [c for c in cases if rx.search(json.dumps(c, ensure_ascii=False))]
    if not hits:
        hits = cases[:n]
    out = []
    for c in hits[:n]:
        out.append(f"- {c.get('client')} ({c.get('sphere')}, {c.get('date')}): "
                   f"{(c.get('narrative') or '')[:420].strip()}  "
                   f"[оборудование: {c.get('equipment')}] [url: {c.get('url')}]")
    return '\n'.join(out)


SHAPE_HINT = {
    'hero': 'Только абзацы <p>. Ни списков, ни таблиц, ни подзаголовков.',
    'text': 'Абзацы <p>, допустим один список <ul> и один <h3>, если это правда помогает.',
    'table': 'Абзацы <p> + ОДНА таблица <table class="colored_table"> с <thead> и <tbody>. '
             'Перед таблицей абзац, объясняющий, что в ней. После таблицы - практический вывод.',
    'price': 'Вводный абзац + блок <div class="price-factors"> с карточками '
             '<div class="price-factor"><span class="price-factor__title">Фактор</span>'
             '<p>пояснение</p></div>. Завершить абзацем-CTA (без кнопки, её ставит сборщик).',
    'steps': 'Вводный абзац + <ol class="steps-list"> с <li><span class="step-title">Название '
             'шага</span> пояснение</li>. Без таблиц.',
    'faq': 'ТОЛЬКО пары строк в формате:\nQ: вопрос\nA: ответ (2-4 предложения)\n'
           'Без HTML, без нумерации. Разметку аккордеона сделает сборщик.',
    'cases': 'Абзацы <p>. По одному абзацу на проект: предприятие, задача, что подобрали. '
             'Ссылку на проект оформить как <a href="URL">название предприятия</a>. '
             'Никаких результатов, которых нет в исходных данных.',
}

SHRINK = """Сократи текст ниже до {vol} знаков без пробелов (сейчас {got} - это перебор).

Что убирать в первую очередь: повторы уже сказанного, вводные обороты, разгон в начале
абзацев, обобщающие фразы без содержания, второй пример там, где хватает одного.
Что сохранить обязательно: все конкретные инженерные факты, таблицы целиком, структуру
и практические выводы. Смысл терять нельзя - только воду.

ФОРМА ВЫВОДА: {shape}

{html}

Верни ТОЛЬКО сокращённый текст, без комментариев.

ТЕКСТ:
{body}"""


PROMPT = """Ты пишешь ОДНУ секцию коммерческой страницы каталога промышленного оборудования
для сайта prokompressor.ru (направление «Компрессор Центр», ООО «Руспром»).

СТРАНИЦА: {h1}
URL: {url}
Что продаём: {intro}

СЕКЦИЯ, которую пишешь сейчас: «{sec_title}»
Задача секции: {sec_task}

⚠️ ОБЪЁМ - ЖЁСТКИЙ ПОТОЛОК, А НЕ ОРИЕНТИР: {vol} знаков без пробелов, максимум {vol_max}.
Это коммерческая страница каталога, а не статья. ТЗ владельца прямо говорит: «Объём не
является целью: не добавлять повторения и общие фразы». Писать плотно: одна мысль - один
абзац, без разгона, без повторного объяснения уже сказанного, без вводных оборотов.
Если материала на потолок не хватает - пиши короче, это правильно.

ФОРМА ВЫВОДА: {shape}

{common}

{style}

{html}

ВНУТРЕННИЕ ССЫЛКИ, которые можно использовать (только если уместно по смыслу, 1-2 на секцию,
анкор естественный, а не рекламный):
{links}

{cases_block}
{tz_block}
Верни ТОЛЬКО содержимое секции. Без заголовка H2, без комментариев, без markdown-обёрток."""


def build_section_prompt(slug: str, page: dict, sec: tuple, cases: list, tz_text: str) -> str:
    title, shape, vol, task = sec
    links = '\n'.join(f'- {u} — анкор вида «{a}»' for u, a in page['links'])
    cases_block = ''
    if shape == 'cases':
        c = cases_for(slug, cases)
        cases_block = ('РЕАЛЬНЫЕ ПРОЕКТЫ КОМПАНИИ (использовать только эти, ничего не '
                       f'придумывать):\n{c}\n\n') if c else ''
    tz_block = ''
    if tz_text:
        # выдаём кусок ТЗ вокруг названия секции - целиком оно не влезает и не нужно
        frag = tz_fragment(tz_text, title)
        if frag:
            tz_block = f'ВЫДЕРЖКА ИЗ ТЗ ВЛАДЕЛЬЦА по этой секции (следовать буквально):\n{frag}\n\n'
    return PROMPT.format(h1=page['h1'], url=page['url'], intro=page['intro'],
                         sec_title=title, vol=vol, vol_max=int(vol * 1.25), sec_task=task,
                         shape=SHAPE_HINT[shape], common=COMMON_RULES, style=STYLE_RULES,
                         html=HTML_RULES, links=links, cases_block=cases_block, tz_block=tz_block)


def tz_fragment(tz: str, title: str, span: int = 2200) -> str:
    """Кусок ТЗ вокруг наиболее похожего заголовка."""
    words = [w.lower() for w in re.findall(r'\w{5,}', title)][:4]
    if not words:
        return ''
    best, best_score = -1, 0
    for m in re.finditer(r'H2:.*', tz):
        line = m.group(0).lower()
        sc = sum(1 for w in words if w[:6] in line)
        if sc > best_score:
            best, best_score = m.start(), sc
    if best < 0 or best_score == 0:
        return ''
    return tz[best:best + span].strip()


# --------------------------------------------------------------------------- #
# Сборка разметки
# --------------------------------------------------------------------------- #

CTA_SVG = ('<i class="svg colored_theme_svg svg-inline-sendmessage" aria-hidden="true">'
           '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="48" viewBox="0 0 40 48">'
           '<defs><style>.cls-1{fill:#095092;fill-rule:evenodd;}</style></defs>'
           '<path class="cls-1" d="M1797,646h40v-3a3,3,0,0,1-3,3h-34a3,3,0,0,1-3-3V601a3,3,0,0,1,'
           '2.99-3H1826l11,11v37h-40Zm30-44v5a1,1,0,0,0,1,1h5Zm8,8h-7a3,3,0,0,1-3-3v-7h-25a1,1,0,0,'
           '0-1,1v42l1,1h34l1-1V610Z" transform="translate(-1797 -598)"></path></svg></i>')


def cta_block(text: str, btn: str, url: str) -> str:
    return f'''  <div class="order-block bordered">
    <div class="row align-items-center">
      <div class="col-md-9 col-sm-8">
        <div class="block-item">
          <div class="flexbox flexbox--row">
            <div class="block-item__image icon_sendmessage">{CTA_SVG}</div>
            <div class="text darken">{text}</div>
          </div>
        </div>
      </div>
      <div class="col-md-3 col-sm-4 btns-col">
        <div class="btns">
          <span class="btn btn-default animate-load" data-event="jqm" data-param-form_id="GET_KP" \
data-name="get_kp" data-autoload-PRODUCT_NAME="Ссылка от куда: https://prokompressor.ru{url}">\
{btn}</span>
        </div>
      </div>
    </div>
  </div>'''


def faq_block(raw: str, prefix: str) -> str:
    pairs = re.findall(r'Q:\s*(.+?)\s*\n\s*A:\s*(.+?)(?=\n\s*Q:|\Z)', raw, re.S)
    out = []
    for i, (q, a) in enumerate(pairs, 1):
        q = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', q)).strip()
        a = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', a)).strip()
        fid = f'{prefix}faq{i}'
        out.append(f'''  <div class="item-accordion-wrapper bordered box-shadow">
    <div class="accordion-head colored_theme_hover_bg-block accordion-close font_md" \
data-toggle="collapse" data-parent="#{fid}" href="#{fid}">
      <span class="arrow_open pull-right colored_theme_hover_bg-el"></span><span>{q}</span>
    </div>
    <div id="{fid}" class="panel-collapse collapse">
      <div class="accordion-body">{a}</div>
    </div>
  </div>''')
    return '\n'.join(out)


def figure(photo: tuple, folder: str) -> str:
    name, alt, _ = photo
    return (f'  <figure>\n'
            f'    <img src="/upload/dm/{folder}/{name}" alt="{alt}" loading="lazy">\n'
            f'    <figcaption class="text-muted small mt-2">{alt}</figcaption>\n'
            f'  </figure>')


def clean(html: str) -> str:
    """Срезает markdown-обёртки и запрещённые теги, которые модель иногда добавляет."""
    html = re.sub(r'^```[a-z]*\s*|\s*```$', '', html.strip())
    html = re.sub(r'(?is)</?(html|body|head|article|section|h1|h2)[^>]*>', '', html)
    html = re.sub(r'\s*style="[^"]*"', '', html)
    html = re.sub(r'—', ' - ', html)                 # длинных тире в проекте нет
    return html.strip()


def assemble(slug: str, page: dict, parts: dict) -> str:
    pre = page['css_prefix']
    folder = slug
    css = open(os.path.join(HERE, 'site-page.css'), encoding='utf-8').read()
    css = css.replace('.dzs-page', f'.{pre}-page')

    L = [f'''<!--
  Статья для страницы: {page['url']}
  H1 «{page['h1']}» задаётся заголовком раздела в CMS и в этот блок НЕ входит.

  Title:       {page['title']}
  Description: {page['description']}

  ФОТО: {len(page['photos'])} шт. в архиве, папка photos-{folder}/.
  Загрузите их на сайт в /upload/dm/{folder}/ - и пути в src совпадут.
  Если папка другая, поменяйте префикс в src у всех img.

  Вёрстка по образцу /catalog/dozhimnye-stantsii-szhatogo-vozdukha/ (сайтовые классы
  colored_table, order-block, accordion-type-1, btn; кастомные - в <style> в конце).
-->
<article class="{pre}-page">''']

    hero_photo = next((p for p in page['photos'] if p[2] == 'hero'), None)
    for i, (title, shape, _vol, _task) in enumerate(page['sections']):
        body = parts.get(title, '')
        if not body:
            continue
        L.append('\n<section>')
        L.append(f'  <h2>{title}</h2>')
        if shape == 'hero' and hero_photo:
            L.append('  <div class="hero-grid">')
            L.append('    <div>')
            L.append(re.sub(r'^', '      ', body, flags=re.M))
            L.append('    </div>')
            L.append(re.sub(r'^', '  ', figure(hero_photo, folder), flags=re.M))
            L.append('  </div>')
        elif shape == 'faq':
            L.append(faq_block(body, pre))
        else:
            L.append(re.sub(r'^', '  ', body, flags=re.M))
            ph = next((p for p in page['photos'] if p[2] == title), None)
            if ph:
                L.append(figure(ph, folder))
        # CTA после первого экрана, после блока цены и в конце
        if shape == 'hero':
            L.append(cta_block(page['cta2'], 'Запросить расчёт', page['url']))
        elif shape == 'price':
            L.append(cta_block('Отправьте параметры потребления - подготовим техническую схему, '
                               'состав оборудования и коммерческое предложение',
                               'Получить расчёт', page['url']))
        L.append('</section>')

    L.append('\n<section>')
    L.append('  <h2>Остались вопросы по подбору?</h2>')
    L.append(f'  <p>Пришлите параметры потребления - расход, требуемую чистоту, давление у '
             f'потребителя и режим работы. Инженер соберёт схему, подберёт состав оборудования '
             f'и подготовит расчёт.</p>')
    L.append(cta_block(page['cta'], 'Получить расчёт', page['url']))
    L.append('</section>\n')
    L.append('</article>\n')
    L.append(f'<style>{css}</style>')
    return '\n'.join(L)


# --------------------------------------------------------------------------- #

def prose_chars(html: str) -> int:
    """Объём БЕЗ таблиц, FAQ, карточек цены и CTA.

    Именно так объём задан в ТЗ владельца: «7 000-9 000 знаков без пробелов + таблицы,
    FAQ, карточки решений и CTA». Первая версия гейта считала всё подряд и показывала
    перебор там, где его не было.
    """
    s = re.sub(r'(?s)<style>.*?</style>', '', html)
    s = re.sub(r'(?s)<!--.*?-->', '', s)
    for rx in (r'(?s)<table.*?</table>',
               r'(?s)<div class="item-accordion-wrapper.*?</div>\s*</div>\s*</div>',
               r'(?s)<div class="price-factors".*?</div>\s*</div>',
               r'(?s)<div class="order-block.*?</div>\s*</div>\s*</div>'):
        s = re.sub(rx, '', s)
    return len(re.sub(r'\s', '', re.sub(r'<[^>]+>', '', s)))


def qa(html: str, page: dict) -> list:
    """Механический гейт перед упаковкой."""
    issues = []
    chars = prose_chars(html)
    lo, hi = page['volume']
    if not lo * 0.85 <= chars <= hi * 1.15:
        issues.append(f'проза {chars} знаков (норма ТЗ {lo}-{hi} без таблиц и FAQ)')
    if '—' in html:
        issues.append('длинное тире')
    bad = re.findall(r'(?i)(лидер рынка|самая низкая цена|широкий спектр|инновацион|'
                     r'в современном мире|идеальное решение|под ключ за)', text)
    if bad:
        issues.append(f'штампы: {sorted(set(b.lower() for b in bad))[:4]}')
    if html.count('<h2>') < len(page['sections']) - 1:
        issues.append(f"секций {html.count('<h2>')} из {len(page['sections']) + 1}")
    for tag in re.findall(r'<(\w+)[^>]*>', html):
        if tag.lower() not in {'article', 'section', 'h2', 'h3', 'p', 'ul', 'ol', 'li', 'strong',
                               'a', 'table', 'thead', 'tbody', 'tr', 'td', 'figure', 'img',
                               'figcaption', 'div', 'span', 'style', 'svg', 'path', 'defs', 'i'}:
            issues.append(f'посторонний тег <{tag}>')
            break
    if 'colored_table' not in html:
        issues.append('нет ни одной таблицы colored_table')
    return issues


def pack(slug: str, page: dict) -> str:
    """Архив: готовый html + картинки под этот slug."""
    art = os.path.join(OUT, f'{slug}.html')
    zpath = os.path.join(OUT, f'{slug}.zip')
    photos_dir = os.path.join(OUT, f'photos-{slug}')
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(art, f'{slug}/article.html')
        readme = (f"{page['h1']}\n\nURL: {page['url']}\nTitle: {page['title']}\n"
                  f"Description: {page['description']}\n\n"
                  f"1) Содержимое article.html вставить в контентный блок страницы {page['url']}.\n"
                  f"   H1 в файл не входит - его ставит заголовок раздела в CMS.\n"
                  f"2) Картинки из папки images/ загрузить в /upload/dm/{slug}/ - пути в src\n"
                  f"   уже прописаны под эту папку.\n")
        z.writestr(f'{slug}/README.txt', readme)
        if os.path.isdir(photos_dir):
            for f in sorted(os.listdir(photos_dir)):
                z.write(os.path.join(photos_dir, f), f'{slug}/images/{f}')
    return zpath


def gen_page(slug: str) -> dict:
    page = PAGES[slug]
    cases = load_cases()
    tz_text = ''
    if page.get('tz'):
        p = os.path.join(HERE, page['tz'])
        if os.path.exists(p):
            tz_text = open(p, encoding='utf-8').read()

    # Бюджет прозы страницы раскидываем по секциям пропорционально их весам из спеки.
    # Иначе сумма ручных цифр живёт своей жизнью: на первом прогоне азотной страницы
    # проза вышла 12 174 знака при норме ТЗ 7000-9000.
    prose_secs = [x for x in page['sections'] if x[1] not in ('faq', 'table')]
    weight = sum(x[2] for x in page['sections'])
    budget = page['volume'][1]
    scale = min(1.0, budget * 1.35 / weight) if weight else 1.0
    print(f'=== {slug}: {len(page["sections"])} секций, бюджет прозы {budget}, '
          f'масштаб секций x{scale:.2f} ===', flush=True)
    parts, models = {}, set()

    def one(sec):
        title, shape, vol0, _ = sec
        vol = max(400, int(vol0 * scale))
        sec = (title, shape, vol, sec[3])
        prompt = build_section_prompt(slug, page, sec, cases, tz_text)
        txt, model = ask(prompt, MAX_TOKENS)
        txt = clean(txt)
        # Модели устойчиво перебирают объём в 1.5-2.5 раза даже с потолком в промпте
        # (первый прогон азотной страницы: 36 108 знаков при норме 7000-9000). Поэтому
        # отдельный проход сжатия, а не надежда на то, что лимит услышат.
        for _ in range(2):
            got = len(re.sub(r'\s', '', re.sub(r'<[^>]+>', '', txt)))
            if got <= vol * 1.12:
                break
            txt, model = ask(SHRINK.format(vol=vol, got=got, shape=SHAPE_HINT[shape],
                                           html=HTML_RULES, body=txt), MAX_TOKENS)
            txt = clean(txt)
        return title, txt, model

    with ThreadPoolExecutor(max_workers=3) as pool:
        for title, body, model in pool.map(one, page['sections']):
            parts[title] = body
            models.add(model)
            print(f'  ✓ {title[:58]:<58} {len(re.sub(chr(60)+"[^"+chr(62)+"]*"+chr(62), "", body))} зн  {model}',
                  flush=True)

    html = assemble(slug, page, parts)
    open(os.path.join(OUT, f'{slug}.html'), 'w', encoding='utf-8').write(html)
    issues = qa(html, page)
    chars = len(re.sub(r'\s', '', re.sub(r'<[^>]+>', '', html)))
    meta = dict(slug=slug, h1=page['h1'], url=page['url'], chars=chars,
                sections=len(parts), models=sorted(models), issues=issues,
                derived=page['derived'])
    json.dump(meta, open(os.path.join(OUT, f'{slug}.meta.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f'  -> {slug}.html  {chars} знаков  '
          f'{"ЧИСТО" if not issues else "issues: " + "; ".join(issues)}', flush=True)
    return meta


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    only = args or list(PAGES)
    if '--pack' in sys.argv:
        for slug in only:
            print(pack(slug, PAGES[slug]))
        return 0
    res = []
    for slug in only:
        try:
            res.append(gen_page(slug))
        except Exception as e:                              # noqa: BLE001
            print(f'{slug}: ПРОВАЛ {repr(e)[:160]}', file=sys.stderr, flush=True)
            res.append(dict(slug=slug, issues=[repr(e)[:160]]))
    rep = ['# Страницы каталога: газогенерация\n']
    for m in res:
        rep.append(f"- `{m['slug']}` | {m.get('chars', '?')} зн | секций {m.get('sections', '?')} | "
                   + ('ЧИСТО' if not m.get('issues') else 'issues: ' + '; '.join(m['issues'])[:200])
                   + (' | структура выведена по аналогии' if m.get('derived') else ''))
    open(os.path.join(OUT, 'REPORT.md'), 'w', encoding='utf-8').write('\n'.join(rep) + '\n')
    print('\n'.join(rep))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
