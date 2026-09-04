# -*- coding: utf-8 -*-
"""Микроразметка «вопрос-ответ» для сниппета Google вида
   «1 ответ · Лучший ответ: ✅ Цены: от 194 035 ₽ ✅ В наличии ✅ Доставка по Москве и РФ».

Такой сниппет даёт ТИП QAPage (не FAQPage): Google подписывает acceptedAnswer как
«Лучший ответ» и выводит текст ответа целиком, вместе с эмодзи-галочками.
FAQPage с августа 2023 в выдаче рисуется только у госсайтов и медицины,
для коммерции расширенного результата не даёт.

Скрипт делает ДВЕ вещи (обе обязательны, иначе разметка = скрытый контент):
  1) видимый на странице блок вопрос-ответ (тот же текст, что и в разметке);
  2) <script type="application/ld+json"> с QAPage.

Числа берём ТОЛЬКО из payload (правило проекта). Цена в статическом блоке -
снимок выгрузки Битрикса: она устаревает, поэтому по умолчанию цена НЕ ставится
(--price static включает её осознанно). Живой вариант - PHP-сниппет в шаблоне
карточки/раздела, см. bitrix-qa-snippet.php и MICRORAZMETKA-SERP.md.

Запуск:
  python3 build_qa_schema.py --one <slug>            # предпросмотр одной страницы
  python3 build_qa_schema.py                          # все 759 -> publish/qa/*.html
  python3 build_qa_schema.py --price static           # с ценой из выгрузки
  python3 build_qa_schema.py --inject                 # дописать блок в publish/schema/*.html
"""
import argparse, glob, json, os, re

DIR = os.path.dirname(os.path.abspath(__file__))
QA = os.path.join(DIR, 'publish', 'qa')
SCHEMA = os.path.join(DIR, 'publish', 'schema')
SITE = 'https://prokompressor.ru'
ORG = 'ООО «Руспром»'

# Маркеры, которые попадают в сниппет. Каждый - утверждение от лица магазина,
# владелец отвечает за его достоверность. Правьте здесь, а не в 759 файлах.
DELIVERY_MARKER = 'Доставка по Москве и России'
EXTRA_MARKERS = []          # напр. ['Гарантия производителя'] - только если это верно для ВСЕХ страниц

BEGIN = '<!-- QA-BLOCK:start (build_qa_schema.py) -->'
END = '<!-- QA-BLOCK:end -->'

RU_MONTHS = {'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
             'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12}


def fmt_price(n):
    return f'{int(n):,}'.replace(',', ' ')


def plural(n, one, few, many):
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def iso_date(ru):
    """«15 июля 2026» -> «2026-07-15»; иначе None."""
    m = re.match(r'(\d{1,2})\s+([а-яё]+)\s+(\d{4})', str(ru or '').strip(), re.I)
    if not m or m.group(2).lower() not in RU_MONTHS:
        return None
    return f'{m.group(3)}-{RU_MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}'


def lower_first(h1):
    """«Поршневые компрессоры Atlas Copco» -> «поршневые…», но «ENGER …» не трогаем."""
    if len(h1) > 1 and h1[1].isupper():
        return h1
    return h1[:1].lower() + h1[1:]


def question_text(payload):
    return f'Почему стоит купить {lower_first(payload.get("h1", "").strip())} в {ORG}?'


def markers(payload, price_mode):
    """Список галочек. Только факты из payload + константы выше."""
    out = []
    if price_mode == 'static' and payload.get('price_min'):
        out.append(f'Цены: от {fmt_price(payload["price_min"])} ₽')
    elif price_mode == 'live':
        out.append('Цены: от {{PRICE_MIN}} ₽')     # плейсхолдер для шаблона Битрикса
    cnt = payload.get('count')
    if cnt:
        # «В продаже», а не «В наличии»: count из выгрузки - позиции каталога с учётом
        # исполнений, а не остаток на складе. Живое «В наличии» умеет только шаблон
        # (bitrix-qa-snippet*.php читает CATALOG_AVAILABLE).
        out.append(f'В продаже: {cnt} {plural(cnt, "позиция", "позиции", "позиций")}')
    out.append(DELIVERY_MARKER)
    out += EXTRA_MARKERS
    return out


def answer_text(payload, price_mode):
    """Первая строка - галочки (её и показывает Google), дальше - обычный ответ."""
    line = ' '.join('✅ ' + m for m in markers(payload, price_mode))
    h1 = payload.get('h1', '').strip()
    # если давление уже названо в H1 - не повторяем его в критериях подбора
    crit = ('фактический расход воздуха' if 'давлен' in h1.lower()
            else 'фактический расход воздуха и давление на участке')
    tail = (f'Подбираем {lower_first(h1)} под {crit}, поставляем со склада '
            f'и под заказ, помогаем с запуском и сервисом.')
    return line + '. ' + tail


def visible_block(payload, price_mode, anchor='qa-answer-1'):
    """Видимый блок: без него QAPage - скрытая разметка и нарушение правил Google."""
    q = question_text(payload)
    a = answer_text(payload, price_mode)
    line, tail = a.split('. ', 1)
    return (f'{BEGIN}\n'
            f'<div class="page-qa" id="qa">\n'
            f'<h2>{q}</h2>\n'
            f'<div id="{anchor}">\n'
            f'<p>{line}.</p>\n'
            f'<p>{tail}</p>\n'
            f'</div>\n'
            f'</div>\n{END}')


def rating_of(slug, ratings):
    """aggregateRating - ТОЛЬКО из реального источника отзывов (reviews-index.json:
       {"<slug>": {"ratingValue": 4.9, "reviewCount": 12}}). Ничего не выдумываем:
       выдуманный рейтинг = ручные санкции «Spammy structured markup»."""
    r = (ratings or {}).get(slug)
    if not r or not r.get('reviewCount'):
        return None
    return {'@type': 'AggregateRating', 'ratingValue': str(r['ratingValue']),
            'reviewCount': int(r['reviewCount']), 'bestRating': '5', 'worstRating': '1'}


def qapage(payload, price_mode, ratings=None, anchor='qa-answer-1'):
    url = SITE + payload.get('url', '')
    q = question_text(payload)
    a = answer_text(payload, price_mode)
    author = {'@type': 'Person', 'name': 'Игорь Волков',
              'url': SITE + (payload.get('byline_url') or '/company/staff/igor-volkov/')}
    answer = {'@type': 'Answer', 'text': a, 'url': f'{url}#{anchor}',
              'upvoteCount': 1, 'author': author}
    d = iso_date(payload.get('review_date'))
    if d:
        answer['dateCreated'] = d
    question = {'@type': 'Question', 'name': q, 'text': q, 'answerCount': 1,
                'acceptedAnswer': answer, 'author': author}
    if d:
        question['dateCreated'] = d
    block = {'@context': 'https://schema.org', '@type': 'QAPage', 'url': url,
             'mainEntity': question}
    ar = rating_of(payload.get('slug', ''), ratings)
    if ar:
        # Звёзды в выдаче даёт рейтинг на Product/Organization, а не на QAPage.
        # На странице-листинге корректная опора - сама организация-продавец.
        block['about'] = {'@type': 'Organization', 'name': ORG, 'url': SITE + '/',
                          'aggregateRating': ar}
    return block


def script_of(block):
    return ('<script type="application/ld+json">\n'
            + json.dumps(block, ensure_ascii=False, indent=1) + '\n</script>')


def render(payload, price_mode, ratings=None):
    return visible_block(payload, price_mode) + '\n\n' + script_of(qapage(payload, price_mode, ratings))


def inject(path, chunk):
    """Идемпотентно: старый блок между маркерами заменяется, а не дублируется."""
    html = open(path, encoding='utf-8').read()
    html = re.sub(re.escape(BEGIN) + r'.*?' + re.escape(END) + r'\s*', '', html, flags=re.S)
    # QA-блок ставим перед JSON-LD, собранным build_schema.py
    i = html.find('<script type="application/ld+json">')
    if i == -1:
        html = html.rstrip() + '\n\n' + chunk + '\n'
    else:
        html = html[:i] + chunk + '\n\n' + html[i:]
    open(path, 'w', encoding='utf-8').write(html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--one', help='slug одной страницы: печать в stdout, без записи')
    ap.add_argument('--price', choices=['none', 'static', 'live'], default='none',
                    help='none - без цены (по умолчанию: снимок выгрузки устаревает); '
                         'static - цена из payload; live - плейсхолдер {{PRICE_MIN}} для шаблона')
    ap.add_argument('--inject', action='store_true', help='дописать блок в publish/schema/*.html')
    args = ap.parse_args()

    ratings = {}
    rp = os.path.join(DIR, 'reviews-index.json')
    if os.path.exists(rp):
        ratings = json.load(open(rp, encoding='utf-8'))
    else:
        print('reviews-index.json не найден -> aggregateRating не ставим (звёзд в выдаче не будет). '
              'Это правильно: рейтинг без реальных отзывов - причина ручных санкций.')

    payloads = sorted(glob.glob(os.path.join(DIR, 'gen', 'payload-*.json')))
    if args.one:
        p = json.load(open(os.path.join(DIR, 'gen', f'payload-{args.one}.json'), encoding='utf-8'))
        print(render(p, args.price, ratings))
        return

    os.makedirs(QA, exist_ok=True)
    n = injected = 0
    for pf in payloads:
        p = json.load(open(pf, encoding='utf-8'))
        slug = p.get('slug') or os.path.basename(pf)[len('payload-'):-len('.json')]
        chunk = render(p, args.price, ratings)
        open(os.path.join(QA, slug + '.html'), 'w', encoding='utf-8').write(chunk + '\n')
        n += 1
        sp = os.path.join(SCHEMA, slug + '.html')
        if args.inject and os.path.exists(sp):
            inject(sp, chunk)
            injected += 1
    print(f'QA-блоков собрано: {n} -> publish/qa/*.html')
    if args.inject:
        print(f'вставлено в publish/schema/*.html: {injected} '
              f'(после каждого прогона build_schema.py вставку надо повторить)')
    if args.price == 'static':
        print('ВНИМАНИЕ: цена статична - снимок выгрузки Битрикса. Перегенерируй блоки '
              'после каждого обновления цен, иначе сниппет разойдётся с ценой на странице.')


if __name__ == '__main__':
    main()
