#!/usr/bin/env python3
"""Приёмка страниц каталога теми же линзами, что и гост-посты, плюс две инженерные.

Владелец 06.08: «прикрути в генерацию статей на сайт все линзы через которые проходит
генерация на донор + вот эти 2 из описания».

До этого у страниц каталога был только механический гейт (`gen_site_page.qa`): объём
прозы, служебные ответы модели, рекламные штампы, битые теги. Ни техники, ни языка,
ни SEO никто не смотрел - в отличие от гост-постов, где приёмка десятью линзами есть
с 04.08.

Что здесь:
  * 8 линз гост-постов переносятся дословно - они без плейсхолдеров и от площадки
    не зависят (engineer, neutral, logic, seo, seo_yandex, seo_google, antiai, language);
  * link и platform переписаны под свой сайт: у страницы каталога не донорская
    площадка и не внешние ссылки, а своя перелинковка и коммерческий интент;
  * teh_technolog и teh_skeptik берутся из finalize_gp (LINZY-TEHPROCESS-opisanie.md).

    python3 finalize_site.py                  # все страницы
    python3 finalize_site.py azotnye-stantsii # точечно
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GP = os.path.join(os.path.dirname(HERE), 'guest-posts')
sys.path.insert(0, HERE)
sys.path.insert(0, GP)
sys.path.insert(0, os.path.dirname(HERE))

import finalize_gp as F                                        # noqa: E402
import gen_site_page as G                                      # noqa: E402
from pages_spec import PAGES                                   # noqa: E402

READY = os.path.join(HERE, 'ready')
MAX_CYCLES = 3
# ПОСЛЕДОВАТЕЛЬНЫЙ ПРОХОД ЛИНЗ - решение владельца 06.08 («последовательно давай,
# нам нужно то 10 статей в день»).
#
# Параллельный вариант (6 потоков) я подал как чистый выигрыш: «линзы друг о друге не
# знают, значит можно звать разом». Цена всплыла на прогоне: все линзы круга судят ОДИН
# снимок текста, а правки применяются по очереди - и если две линзы метят в одно место,
# цитата второй уже не совпадает с изменённым текстом. В логе это выглядело как 0/4
# применённых правок почти у каждой линзы.
#
# Здесь каждая линза видит текст ПОСЛЕ правок предыдущей, поэтому цитата всегда
# актуальна. Медленнее примерно втрое (12 линз подряд вместо шести парами), но 10 статей
# в день это выдерживает, а терять правки нельзя.

# Линзы, которые переносятся без единой правки: они судят текст, а не площадку.
SHARED = ['engineer', 'neutral', 'logic', 'seo', 'seo_yandex', 'seo_google',
          'antiai', 'language']

SITE_LENSES = {
'link': """Ты - редактор каталога и специалист по внутренней перелинковке.
Проверь ССЫЛОЧНЫЙ БЛОК коммерческой страницы каталога prokompressor.ru.
Внутренние ссылки на разделы каталога: {links_info}
Смотри: ссылка ведёт туда, куда обещает якорь; якорь читается как часть фразы, а не
вставлен насильно; нет ссылки в первом абзаце; на одну и ту же страницу не ссылаемся
дважды; ссылок на страницы проектов не больше, чем кейсов в тексте. Отдельно проверь,
что нет ссылок на несуществующие разделы и на конкурентов.""",

'platform': """Ты - выпускающий редактор сайта prokompressor.ru («Компрессор Центр»).
Это КОММЕРЧЕСКАЯ страница каталога, а не информационная статья и не гостевой пост.
Проверь: страница закрывает коммерческий интент в первых 800-1200 знаках (что
поставляется, чем отличается от соседних категорий, по каким данным считается);
после каждого технического блока есть практический вывод - что это меняет при подборе
и какие данные запросить у заказчика; нет лозунгов «лучшее решение», «самая низкая
цена», «моментальная окупаемость»; нет пересказа школьной химии и энциклопедии;
не заявлены точная чистота, расход, давление, точка росы, срок изготовления или
окупаемости без привязки к конфигурации. Байлайн и подпись автора на странице каталога
не нужны.""",
}

# ── Стилевой канон страниц каталога ────────────────────────────────────────────
# Владелец 06.08: «стиль письма такой же нужен только для статей на сайт, для гост-постов
# пусть будет как было». До этого канон применялся только на ГЕНЕРАЦИИ (эталонная статья
# дожимных станций + ТЗ), а приёмочные линзы судили по своим персонам и о нём не знали.
# Замеры по эталону: медиана 16 слов на абзац (разброс 9-51), медиана 1 предложение
# на абзац, определения через тире, «вы/ваш» к читателю, числа диапазонами.
STYLE_ANCHOR = """

=== СТИЛЕВОЙ КАНОН СТРАНИЦЫ (обязателен, правки против него запрещены) ===
Эталон - страница «Дожимные станции сжатого воздуха» того же каталога.
* Тон: спокойный инженерно-деловой разбор. Не реклама, не инструкция производителя,
  не научная статья. Обращение к читателю на «вы» уместно.
* Абзац короткий: медиана 16 слов, одно-два предложения. Длинных периодов не строить.
* Определение даётся через тире: «Дожимная станция - это готовый к подключению комплекс».
* Числа - диапазонами с единицами («4-10 бар», «30-40 бар»), без «примерно» и «порядка».
* Запрещено: длинное тире (только дефис), лозунги («лучшее решение», «самая низкая цена»),
  школьная химия, пересказ энциклопедии, точные чистота/расход/давление/срок окупаемости
  без привязки к конфигурации.
* После технического блока - практический вывод: что это меняет при подборе и какие
  данные запросить у заказчика.

ЗАПРЕТ НА ПЕРЕПИСЫВАНИЕ: правки только точечные, по существу претензии. Менять формулировку
ради «звучит лучше» нельзя. Если замена меняет тон или ритм абзаца - не предлагай её.
Заголовки H2 не трогать вообще: структура задана техническим заданием владельца."""


def links_of(html: str) -> str:
    urls = re.findall(r'href="(/[^"]+|https://prokompressor\.ru/[^"]+)"', html)
    uniq = list(dict.fromkeys(urls))
    return '; '.join(uniq[:12]) or '(внутренних ссылок нет)'


def run_lens(name: str, body: str, html: str, confirm=False):
    tpl = SITE_LENSES.get(name) or F.LENSES[name]
    head = tpl.format(links_info=links_of(html)) if '{links_info}' in tpl else tpl
    head += STYLE_ANCHOR
    extra = F.CONFIRM_NOTE if confirm else ''
    out, judge = F.call_judge(head + F.FMT + extra + '\n\n=== СТАТЬЯ ===\n' + body)
    passed, edits = F.parse_verdict(out)
    edits = [(q, r.replace('—', '-'), w) for q, r, w in edits]
    return passed, edits, out, judge


def in_heading(body: str, quote: str) -> bool:
    """Цитата попадает внутрь <h2>/<h3>?

    Просьбы в промпте мало: заголовки задаёт ТЗ владельца, и переписывать их линзе
    незачем. На гост-постах SEO-линза переформулировала 3 заголовка из 6 в вопросную
    форму - для страниц каталога это недопустимо, поэтому запрет механический.
    """
    for m in re.finditer(r'(?s)<h[23]>(.*?)</h[23]>', body):
        if quote and quote in m.group(1):
            return True
    return False


def finalize(slug: str) -> bool:
    page = PAGES[slug]
    body = open(os.path.join(HERE, f'{slug}.html'), encoding='utf-8').read()
    log = [f'# Приёмка страницы {slug} ({page["url"]})\n']
    order = ['link', 'platform'] + SHARED + ['teh_technolog', 'teh_skeptik']
    pending, applied_total = list(order), 0

    for cycle in range(1, MAX_CYCLES + 1):
        log.append(f'\n## Круг {cycle}: {", ".join(pending)}\n')
        still = []
        for name in pending:
            passed, edits, out, judge = run_lens(name, body, body, confirm=(cycle > 1))
            if name.startswith('teh_'):
                tv = re.search(r'ТЕХВЕРДИКТ:\s*(\w+)', out)
                tv = tv.group(1).lower() if tv else '?'
                log.append(f'- [{name}] техвердикт: {tv}')
                print(f'  [{name}] техвердикт: {tv}', flush=True)
                if tv == 'сомнительно':
                    note = re.sub(r'(?s).*ТЕХВЕРДИКТ:\s*\w+', '', out).strip()[:300]
                    log.append(f'  > СОМНЕНИЕ, решает человек: {note}')
                    passed = True
            n_app = 0
            for quote, repl, why in edits:
                if in_heading(body, quote):
                    log.append(f'- [{name}] ОТКЛОНЕНА правка заголовка: «{quote[:70]}…» '
                               f'(H2/H3 заданы ТЗ, менять нельзя)')
                    continue
                q = quote if quote in body else None
                if q is None:
                    pat = re.sub(r'(\\ )+', r'\\s+', re.escape(quote))
                    m = re.search(pat, body)
                    q = m.group(0) if m else None
                if q is not None:
                    body = body.replace(q, repl, 1)
                    n_app += 1
                    log.append(f'- [{name}] применено: «{quote[:70]}…» -> «{repl[:70]}» ({why})')
                else:
                    log.append(f'- [{name}] НЕ НАЙДЕНА цитата: «{quote[:80]}…»')
            applied_total += n_app
            status = 'PASS' if passed else f'FAIL, правок применено {n_app}/{len(edits)}'
            print(f'  [{name}] {status} (судья {judge})', flush=True)
            log.append(f'- [{name}] вердикт: {status} (судья {judge})')
            if not passed:
                if not n_app:
                    log.append(f'\n<details><summary>сырой вердикт {name}</summary>\n\n{out}\n</details>')
                still.append(name)
        issues = G.qa(body, page)
        log.append(f'- мех-гейт после правок: {"; ".join(issues) if issues else "чисто"}')
        if issues:
            print(f'  мех-гейт: {"; ".join(issues)[:110]}', flush=True)
        pending = still
        if not pending:
            break

    ok = not pending and not G.qa(body, page)
    os.makedirs(READY, exist_ok=True)
    name = f'{slug}.final.html' if ok else f'{slug}.NEEDS-REVIEW.html'
    open(os.path.join(READY, name), 'w', encoding='utf-8').write(body)
    verdict = 'ГОТОВА К ПУБЛИКАЦИИ' if ok else f'ТРЕБУЕТ ВЗГЛЯДА (не сошлись: {", ".join(pending)})'
    log.insert(1, f'**Итог: {verdict}. Правок применено: {applied_total}. Файл: ready/{name}**')
    open(os.path.join(READY, f'{slug}.finalize-log.md'), 'w', encoding='utf-8').write('\n'.join(log))
    print(f'=> ready/{name} | {verdict}')
    return ok


def main() -> int:
    want = [a for a in sys.argv[1:] if not a.startswith('--')]
    slugs = want or list(PAGES)
    print(f'приёмка {len(slugs)} страниц, линз на страницу: '
          f'{len(SITE_LENSES) + len(SHARED) + 2}')
    for s in slugs:
        if not os.path.exists(os.path.join(HERE, f'{s}.html')):
            print(f'{s}: файла нет, пропуск')
            continue
        print(f'=== {s} ===', flush=True)
        finalize(s)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
