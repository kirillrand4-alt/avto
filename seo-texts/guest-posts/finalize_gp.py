# -*- coding: utf-8 -*-
"""Финальная приёмка гост-поста: статья -> мех-QA -> 6 линз -> правки -> ГОТОВЫЙ текст.

    PROVIDER_DEAD_MODELS='' PROVIDER_FIRST_TOKEN_SEC=240 python3 finalize_gp.py <slug>[.variant] ...
    (например: finalize_gp.py dizel-na-strojke  или  finalize_gp.py dizel-na-strojke.gpt)

Набор линз построен 03.08.2026 методом «идеи от 4 ИИ + судья от каждого ИИ»
(fable-5, gemini-3.1-pro, gpt-5.6-terra, grok-4.5; сырьё - LENS-IDEAS.md, вердикты
судей - LENS-JUDGES.md). В набор вошли кластеры, поддержанные 2-3 судьями; идеи
судей fable и gpt о сверке якоря с посадочной страницей влиты в L1; grok-судья
пересказал пул вместо критики - его вклад нулевой (честно).

Механика: каждая линза обязана вернуть строгий формат
    ВЕРДИКТ: PASS   |   ВЕРДИКТ: FAIL + правки «"точная цитата" -> "замена"»
Правки с точной цитатой применяются ДЕТЕРМИНИРОВАННО кодом (replace), затем мех-QA
и подтверждающий круг только по FAIL-линзам. Максимум 2 круга. Итог:
ready/gp-<имя>.final.html (или .NEEDS-REVIEW.html, если линзы не сошлись) + лог."""
import json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen_provider as gp
from gen_wave import JOBS, qa_multi, _openai_stream

DIR = os.path.dirname(os.path.abspath(__file__))
READY = os.path.join(DIR, 'ready')
JUDGES = ['claude-fable-5', 'claude-opus-4-8', 'openai:gemini-3.6-flash']
MAX_CYCLES = 3

FMT = """
ПОРОГ: PASS - вердикт по умолчанию. FAIL ставь ТОЛЬКО если без правки статью нельзя
отдавать на публикацию (фактическая/техническая ошибка, опасный совет, рекламный флёр,
битая логика, опечатка, обман читателя). «Можно улучшить», вкусовые и стилистические
предпочтения = PASS. Придирки ради придирок запрещены.

Формат ответа СТРОГО:
Первая строка: ВЕРДИКТ: PASS   (если обязательных правок нет)
или:           ВЕРДИКТ: FAIL
затем каждая правка отдельной строкой:
"точная цитата из текста" -> "замена" | причина в 3-7 словах
Цитата обязана присутствовать в тексте ДОСЛОВНО (копируй, не пересказывай), иначе
правка не применится. Замена - готовый текст на то же место (пустая строка "" =
удалить). В замене ЗАПРЕЩЕНО длинное тире - только дефис. Максимум 4 правки."""

CONFIRM_NOTE = ('\nЭто ПОДТВЕРЖДАЮЩИЙ круг: статья уже исправлена по замечаниям линз. '
                'Подтверди приёмку (PASS), FAIL - только если осталась критическая проблема.\n')

LENSES = {
'link': """ВАЖНО: имя бренда ВНУТРИ текста-якоря ссылки разрешено (брендовый якорь по анкор-плану), вне якорей - нет.
Ты - линкбилдер и выпускающий редактор. Проверь ССЫЛОЧНЫЙ БЛОК статьи:
якорь звучит естественно и не обещает того, чего нет на целевой странице {links_info};
абзац со ссылкой самодостаточен (смысл цел без ссылки); нет конструкций-интриг «читайте
здесь»/«узнать подробнее» и рекламных подводок; ссылка подана как источник/справка.""",
'platform': """ВАЖНО: имя бренда ВНУТРИ текста-якоря ссылки <a>...</a> разрешено (брендовый якорь по анкор-плану) - это не рекламный флёр. Бренд вне якорей - нарушение.
Ты - выпускающий редактор площадки {donor} ({donor_note}). Проверь ПОПАДАНИЕ
В ПЛОЩАДКУ: жанр и тон соответствуют изданию (не инструкция производителя, не карточка
товара); региональный/аудиторный контекст уместен и не выглядит заплаткой; заголовок и
лид отвечают формату площадки; нет фрагментов, чужеродных для читателя площадки.""",
'engineer': """Ты - главный инженер по компрессорному оборудованию и пневмосистемам (20 лет).
Проверь ТЕХНИКУ И БЕЗОПАСНОСТЬ: физические зависимости верны (давление/производительность,
цепочка подготовки воздуха, единицы измерения); термины не перепутаны; советы не опасны -
где нужно, стоит предупреждение (например, азот в замкнутом помещении = риск асфиксии,
сосуды под давлением); нет универсальных советов там, где нужен расчёт.""",
'neutral': """ВАЖНО: имя бренда ВНУТРИ текста-якоря ссылки <a>...</a> разрешено (брендовый якорь по анкор-плану) - это не рекламный флёр. Бренд вне якорей - нарушение.
Ты - аудитор рекламной нейтральности. Проверь, что статья НЕ читается как
реклама: нет призывов к действию (купить/заказать/обратитесь); нет оценочных прилагательных
рядом с брендами и ссылками (лучший/идеальный/ведущий); нет структуры «проблема - и вот
единственное решение по ссылке»; нет гарантий и категоричных обещаний (окупится за/сэкономит
ровно); упомянуты альтернативы или условия, а не один путь.""",
'logic': """Ты - редактор-логик. Проверь ЦЕПОЧКУ ДЛЯ ЧИТАТЕЛЯ: заголовок обещает то, что текст
даёт; каждый совет вытекает из названных условий (нет советов из ниоткуда); нет смысловых
разрывов между разделами; финал - итог, а не обрыв и не повтор; читатель в конце знает свой
следующий шаг.""",
'language': """Ты - корректор и стилист-носитель русского. Проверь ЯЗЫК ТОЧЕЧНО: опечатки и
склейки слов (типа «в трубахночью», «на78%»); кальки и канцелярские конструкции (номинализации,
«осуществляется проведение»); шаблонные AI-переходы; неестественные коллокации. Только
конкретные правки цитатой, стиль в целом не переписывать.""",
}


def call_judge(prompt):
    last = None
    for model in JUDGES:
        for a in range(2):
            if a:
                time.sleep(10)
            try:
                if model.startswith('openai:'):
                    text, _ = _openai_stream([{'role': 'user', 'content': prompt}], model[7:], 4000)
                else:
                    msg = gp._raw_stream([{'role': 'user', 'content': prompt}], model, 4000,
                                         thinking=False, effort=None)
                    text = ''.join(b.text for b in msg.content if b.type == 'text')
                if text.strip():
                    return text.strip(), model
                last = f'{model}: пусто'
            except Exception as e:
                last = f'{model}: {repr(e)[:80]}'
    raise RuntimeError(f'судьи исчерпаны: {last}')


def parse_verdict(out):
    """-> (passed: bool, edits: [(цитата, замена, причина)])"""
    passed = bool(re.search(r'ВЕРДИКТ:\s*PASS', out))
    edits = []
    for m in re.finditer(r'"((?:[^"\\]|\\.){4,}?)"\s*->\s*"((?:[^"\\]|\\.)*?)"(?:\s*\|\s*(.+))?$',
                         out, re.M):
        edits.append((m.group(1), m.group(2), (m.group(3) or '').strip()))
    # судьи цитируют HTML с кавычками внутри через `бэктики` - второй формат
    for m in re.finditer(r'`([^`]{4,}?)`\s*->\s*`([^`]*?)`(?:\s*\|\s*(.+))?$', out, re.M):
        edits.append((m.group(1), m.group(2), (m.group(3) or '').strip()))
    return passed, edits


def run_lens(name, body, job, confirm=False):
    links_info = '; '.join(f'{u} (якорь должен быть про: {a})' for u, a in job['links'])
    head = LENSES[name].format(donor=job['donor'], donor_note=job['donor_note'],
                               links_info=links_info)
    extra = CONFIRM_NOTE if confirm else ''
    out, judge = call_judge(head + FMT + extra + '\n\n=== СТАТЬЯ ===\n' + body)
    passed, edits = parse_verdict(out)
    # санитизация замен: судьи протаскивают запрещённые символы (смоук 03.08)
    edits = [(q, r.replace('—', '-').replace('<ul>', '').replace('<li>', ''), w)
             for q, r, w in edits]
    return passed, edits, out, judge


def finalize(fname):
    base = re.sub(r'\.html$', '', fname)
    slug = re.sub(r'\.(gemini|gpt|claude)$', '', base.replace('gp-', ''))
    job = next((j for j in JOBS if j['slug'] == slug), None)
    if job is None:
        sys.exit(f'нет JOBS-контекста для {slug}')
    html = open(os.path.join(DIR, base + '.html'), encoding='utf-8').read()
    title, body = html.split('</h1>\n', 1)
    log = [f'# Финализация {base} (донор {job["donor"]})\n']
    pending = list(LENSES)
    applied_total = 0
    for cycle in range(1, MAX_CYCLES + 1):
        log.append(f'\n## Круг {cycle}: линзы {", ".join(pending)}\n')
        still_fail = []
        for name in pending:
            passed, edits, out, judge = run_lens(name, body, job, confirm=(cycle > 1))
            n_app = 0
            for quote, repl, why in edits:
                q = quote if quote in body else None
                if q is None:   # цитата с нормализованными пробелами (судьи схлопывают)
                    import re as _re
                    pat = _re.escape(quote)
                    pat = _re.sub(r'(\\ )+', r'\\s+', pat)
                    m2 = _re.search(pat, body)
                    q = m2.group(0) if m2 else None
                if q is not None:
                    body = body.replace(q, repl, 1)
                    n_app += 1
                    log.append(f'- [{name}] применено: «{quote[:70]}…» -> «{repl[:70]}» ({why})')
                else:
                    log.append(f'- [{name}] НЕ НАЙДЕНА цитата: «{quote[:80]}…» (пропущена)')
            applied_total += n_app
            status = 'PASS' if passed else f'FAIL, правок применено {n_app}/{len(edits)}'
            print(f'  [{name}] {status} (судья {judge})', flush=True)
            log.append(f'- [{name}] вердикт: {status} (судья {judge})')
            if not passed and not n_app:
                # FAIL без применимых правок - оставляем на решение человека
                log.append(f'\n<details><summary>сырой вердикт {name}</summary>\n\n{out}\n</details>')
                still_fail.append(name)
            elif not passed:
                still_fail.append(name)   # применили правки - подтвердить на следующем круге
        issues = qa_multi(body, job['links'])
        if issues:
            log.append(f'- мех-QA после правок: {"; ".join(issues)}')
            print(f'  мех-QA: {"; ".join(issues)[:120]}', flush=True)
        else:
            log.append('- мех-QA после правок: чисто')
        pending = still_fail
        if not pending:
            break
    ok = not pending and not qa_multi(body, job['links'])
    os.makedirs(READY, exist_ok=True)
    out_name = f'{base}.final.html' if ok else f'{base}.NEEDS-REVIEW.html'
    open(os.path.join(READY, out_name), 'w', encoding='utf-8').write(title + '</h1>\n' + body)
    verdict = 'ГОТОВ К ПУБЛИКАЦИИ' if ok else f'ТРЕБУЕТ РУЧНОГО ВЗГЛЯДА (не сошлись: {", ".join(pending)})'
    log.insert(1, f'**Итог: {verdict}. Правок применено: {applied_total}. Файл: ready/{out_name}**')
    open(os.path.join(READY, f'{base}.finalize-log.md'), 'w', encoding='utf-8').write('\n'.join(log))
    print(f'=> ready/{out_name} | {verdict}')
    return ok


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        sys.exit('usage: finalize_gp.py <slug>[.gemini|.gpt] ...')
    for a in args:
        name = a if a.startswith('gp-') else 'gp-' + a
        print(f'=== {name} ===', flush=True)
        finalize(name)


if __name__ == '__main__':
    main()
