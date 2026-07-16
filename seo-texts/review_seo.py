# -*- coding: utf-8 -*-
"""SEO-ревью сгенерированных текстов «глазами Яндекса и Гугла» через провайдерский API (Fable).
Оценка: что ОПАСНО/ВРЕДНО (риски фильтров/санкций), что ПОЛЕЗНО, чего НЕ ХВАТАЕТ.
Смотрит на ВЕСЬ подход (массовая генерация 759 страниц), не на один текст."""
import json, os, re, sys, glob
import gen_provider as gp

DIR = os.path.dirname(os.path.abspath(__file__))


def readable(slug):
    d = json.load(open(os.path.join(DIR, f'gen/result-{slug}.json')))
    p = json.load(open(os.path.join(DIR, f'gen/payload-{slug}.json')))
    txt = re.sub(r'<[^>]+>', ' ', d['text_html'])
    txt = re.sub(r'\s+', ' ', txt.replace('&nbsp;', ' ')).strip()
    kind = ('бренд ' + str(p.get('page_brand'))) if p.get('page_brand') else ('фасет ' + str(p.get('facet_value') or p.get('facet_dimension') or ''))
    links = re.findall(r'href="([^"]+)"', d['text_html'])
    return (f'### СТРАНИЦА: {p["h1"]}\n'
            f'URL: {p["url"]} | тип: {p["category"]}/{kind} | {len(txt)} знаков\n'
            f'внутренние ссылки: {links}\n'
            f'ТЕКСТ:\n{txt}\n')


YANDEX = """Ты - ведущий SEO-аналитик, специализация: РАНЖИРОВАНИЕ В ЯНДЕКСЕ (рунет, коммерческие категории).
Знаешь наизусть: фильтр Баден-Баден (переоптимизация/тексты-для-роботов), переспам и заспамленность,
текстовую релевантность, поведенческие и коммерческие факторы, ИКС, шаблонность/малополезность,
дубли и почти-дубли на близких фасетах, требования к SEO-текстам категорий в 2026.

Перед тобой ОБРАЗЦЫ текстов из МАССОВОЙ генерации ~760 страниц каталога промышленных компрессоров и
оборудования подготовки воздуха. Все страницы делаются по одному конвейеру (общие скелеты структуры,
единый тон, брендовые факты, реальные проекты-кейсы, внутренняя перелинковка, FAQ-аккордеон).

Оцени ГЛАЗАМИ ЯНДЕКСА и выдай строго по разделам:
1. ОПАСНО/ВРЕДНО - что реально грозит фильтром/пессимизацией (Баден-Баден, переспам, шаблонность,
   близкие дубли между фасетами 8/10/12 бар и т.п.). Ранжируй по риску. Для каждого - конкретный пример из текстов.
2. ПОЛЕЗНО - что Яндекс зачтёт в плюс (реальные кейсы, коммерческие факторы, релевантность, перелинковка).
3. ЧЕГО НЕ ХВАТАЕТ - что добавить для ранжирования (микроразметка, коммерческие сигналы, уникализация
   близких фасетов, поведенческие крючки и т.п.).
4. ВЕРДИКТ по массовому запуску 760 страниц: риск-уровень (низкий/средний/высокий) и 3-5 приоритетных правок.
Пиши конкретно, без воды. Ты отвечаешь за то, чтобы сайт НЕ попал под фильтр."""

GOOGLE = """You are a senior SEO analyst focused on GOOGLE ranking (2026), expert in: Helpful Content System /
people-first content, E-E-A-T (Experience/Expertise/Authoritativeness/Trust), the spam policies -
especially SCALED CONTENT ABUSE (mass AI-generated pages) from the March 2024 update, thin/duplicate
content, keyword stuffing, unnatural internal linking, and programmatic SEO done right vs wrong.

Before you: SAMPLE texts from a MASS generation of ~760 catalog pages (industrial compressors + air-prep
equipment), all produced by one pipeline (shared structural skeletons, unified tone, gated brand facts,
REAL delivered-project case studies with links, internal linking, FAQ accordion). Texts are in Russian;
review them as Google would for a ru-market site.

Assess THROUGH GOOGLE'S EYES, strictly by sections (write in Russian for the client):
1. ОПАСНО/ВРЕДНО - what genuinely risks a penalty/demotion. Rank by severity. The elephant: is this
   "scaled content abuse"? What saves it or dooms it? Give concrete examples from the texts.
2. ПОЛЕЗНО - what Google rewards here (real Experience via projects = E-E-A-T, helpfulness, intent coverage).
3. ЧЕГО НЕ ХВАТАЕТ - what to add (structured data / schema, author/trust signals, unique value per page,
   query-intent gaps).
4. ВЕРДИКТ on launching 760 pages: risk level (low/medium/high) and the 3-5 highest-priority fixes.
Be concrete and specific, cite the texts. You are accountable for keeping the site out of a Helpful-Content demotion."""


def main():
    slugs = [l.strip() for l in open(os.path.join(DIR, sys.argv[1])) if l.strip()] if len(sys.argv) > 1 else []
    if not slugs:
        # по умолчанию: 3 компрессорных пилота + несколько некомпрессорных из готовых
        slugs = ['vintovye__elektricheskie_1__remeza', 'vintovye__dizelnye__remeza',
                 'po-tipu__vintovye__kompressory-40-bar']
        for s in ['catalog__osushiteli__refrizheratornye', 'catalog__resivery__airpol_resiver',
                  'catalog__podgotovka-vozdukha__filtry-magistralnye']:
            if os.path.exists(os.path.join(DIR, f'gen/result-{s}.json')):
                slugs.append(s)
    corpus = '\n\n'.join(readable(s) for s in slugs if os.path.exists(os.path.join(DIR, f'gen/result-{s}.json')))
    client = gp.make_client()
    for name, persona in [('yandex', YANDEX), ('google', GOOGLE)]:
        prompt = persona + '\n\n=== ОБРАЗЦЫ ТЕКСТОВ ===\n' + corpus
        print(f'--- запуск ревьюера {name} ({len(prompt)//4} токенов вход) ---', file=sys.stderr)
        msg = gp.call(client, [{'role': 'user', 'content': prompt}], model='claude-fable-5')
        text = ''.join(b.text for b in msg.content if b.type == 'text').strip()
        open(os.path.join(DIR, f'review-{name}.md'), 'w', encoding='utf-8').write(text)
        print(f'--- {name}: {len(text)} знаков, out={msg.usage.output_tokens} ток ---', file=sys.stderr)


if __name__ == '__main__':
    main()
