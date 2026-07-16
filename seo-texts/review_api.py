# -*- coding: utf-8 -*-
"""SEO-ревью текстов через провайдерский API (Fable 5): «насколько текст понравится поисковикам».
Использование: python3 review_api.py <result.json> [<result.json> ...]
Результат: рядом с каждым файлом - review-<имя>.json + сводка в stdout."""
import json, os, re, sys

from gen_provider import make_client, call

DIR = os.path.dirname(os.path.abspath(__file__))

PROMPT = """Ты - жёсткий SEO-аудитор коммерческих текстов для Яндекса и Google (стандарты 2025-2026:
E-E-A-T, полезный контент, антиспам, детекторы ИИ-текстов). Оцени SEO-текст нижнего блока
страницы каталога промышленных компрессоров.

=== СТРАНИЦА ===
URL: {url}
H1 (остаётся текущий): {h1}

=== ДАННЫЕ, НА КОТОРЫХ ПИСАЛСЯ ТЕКСТ (проверь заземлённость фактов) ===
{payload_short}

=== ТЕКСТ (HTML) ===
{html}

Оцени по шкале 1-10 каждый критерий (10 = идеально для ПС):
1. intent_match - соответствие интенту страницы (коммерческий листинг + консультация)
2. usefulness - реальная полезность для покупателя (инженер/снабженец), а не «вода для ПС»
3. expertise - экспертность: конкретика, цифры, серии, отсутствие пустых обобщений
4. naturalness - естественность языка: НЕ выглядит ли ИИ-текстом (штампы, ровный ритм,
   канцелярит, переспам ключей); burstiness
5. spam_risk - риск антиспама наоборот (10 = риска нет): тошнота, переоптимизация,
   коммерческие накрутки, скрытые манипуляции
6. structure - структура: H2, списки, FAQ, перелинковка (уместность и анкоры)
7. grounding - заземлённость: все факты/цифры соответствуют данным payload, ничего не выдумано

Затем:
- top_issues: до 5 самых важных проблем с цитатами (что именно снизит позиции/доверие)
- quick_wins: до 3 быстрых улучшений с наибольшим эффектом
- verdict_1_10: итоговая оценка «понравится ли поисковикам»
- would_rank: честный прогноз одним предложением

Ответь ОДНИМ JSON: {{"intent_match": N, "usefulness": N, "expertise": N, "naturalness": N,
"spam_risk": N, "structure": N, "grounding": N, "verdict_1_10": N,
"top_issues": ["..."], "quick_wins": ["..."], "would_rank": "..."}}"""


def short_payload(payload):
    keep = {k: payload.get(k) for k in ('slug', 'h1', 'tier', 'skeleton', 'el_count', 'price_min',
                                        'price_max', 'pressure_bar', 'sample_models_cheap',
                                        'series_observed', 'brands_in_facet', 'brand_facts', 'projects')}
    return json.dumps(keep, ensure_ascii=False)[:6000]


def main():
    client = make_client()
    rows = []
    for path in sys.argv[1:]:
        d = json.load(open(path))
        slug = d['slug']
        ppath = os.path.join(DIR, f'gen/payload-el-{slug}.json')
        payload = json.load(open(ppath)) if os.path.exists(ppath) else {}
        prompt = PROMPT.format(url=d.get('url', ''), h1=d.get('h1', ''),
                               payload_short=short_payload(payload), html=d['text_html'])
        msg = call(client, [{'role': 'user', 'content': prompt}], 'claude-fable-5')
        text = ''.join(b.text for b in msg.content if b.type == 'text').strip()
        text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text)
        m = re.search(r'\{.*\}', text, re.S)
        rev = json.loads(m.group(0))
        out = os.path.join(os.path.dirname(path), f'review-{os.path.basename(path)}')
        json.dump(rev, open(out, 'w'), ensure_ascii=False, indent=1)
        rows.append((path, rev))
        print(f"{path}: вердикт {rev.get('verdict_1_10')}/10 "
              f"(польза {rev.get('usefulness')}, естественность {rev.get('naturalness')}, "
              f"заземлённость {rev.get('grounding')})", flush=True)
    print('\n=== СВОДКА ===')
    for path, rev in rows:
        print(f"\n--- {path}")
        print('  прогноз:', rev.get('would_rank', ''))
        for i in rev.get('top_issues', [])[:3]:
            print('  проблема:', i[:160])


if __name__ == '__main__':
    main()
