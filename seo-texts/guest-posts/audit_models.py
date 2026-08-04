# -*- coding: utf-8 -*-
"""Сравнительный аудит трёх модельных версий каждой статьи волны 1 линзами провайдера.

    PROVIDER_DEAD_MODELS='' PROVIDER_FIRST_TOKEN_SEC=240 python3 audit_models.py

По каждой теме судья получает ВСЕ ТРИ версии вслепую (A=клод, B=gemini, C=gpt -
судье маппинг не сообщается) и ранжирует. Три линзы: SEO-пригодность, релевантность
донору, качество текста (инженер+редактор). Судья: fable-5 (ожил на ревью-задачах
03.08 вечером), фолбэк opus-4-8 -> gemini-3.6-flash. Выход: audit-models-report.md."""
import os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen_provider as gp
from gen_wave import JOBS, _openai_stream

DIR = os.path.dirname(os.path.abspath(__file__))
JUDGES = ['claude-fable-5', 'claude-opus-4-8', 'openai:gemini-3.6-flash']
VARIANTS = [('A', ''), ('B', '.gemini'), ('C', '.gpt')]   # маппинг НЕ сообщается судье

LENSES = {
'seo': """Ты - SEO-аудитор гостевых публикаций (Яндекс + Google). Ниже три варианта (A, B, C)
ОДНОЙ статьи для размещения на стороннем сайте со ссылками на сайт-акцептор. Оцени КАЖДЫЙ
вариант по осям (каждая 1-10): переспам/риск Баден-Бадена; естественность ссылок и якорей
(положение, контекст, коммерческость); полезность читателю по меркам Helpful Content;
машинность текста как SEO-риск (ровный ритм, шаблонные конструкции); структура и объём для
гост-поста. Затем итоговый балл 1-10 каждому, ранжирование и 2-3 предложения обоснования
на вариант. Не гадай, какой моделью написан текст, оценивай только текст.
В САМОМ КОНЦЕ отдельной строкой: ПОБЕДИТЕЛЬ: <A|B|C>""",
'donor': """Ты - выпускающий редактор площадки {donor} ({donor_note}) и одновременно консультант
по link-building. Ниже три варианта (A, B, C) ОДНОЙ статьи, предложенной твоей площадке как
гостевой материал. Оцени КАЖДЫЙ (1-10 по осям): органичность для аудитории площадки;
самодостаточность и нерекламность (возьмёшь ли без правок, не потребует ли маркировки);
уместность и незаметность ссылок для читателя; риск для площадки (выглядит ли покупным).
Итоговый балл каждому, ранжирование, 2-3 предложения на вариант.
В САМОМ КОНЦЕ отдельной строкой: ПОБЕДИТЕЛЬ: <A|B|C>""",
'quality': """Ты - двойная комиссия: главный инженер по компрессорному оборудованию (20 лет) и
литературный редактор-носитель русского. Ниже три варианта (A, B, C) ОДНОЙ статьи. Оцени
КАЖДЫЙ (1-10 по осям): техническая корректность (физика сжатого воздуха, подбор, отсутствие
опасных советов - если есть фактическая ошибка, укажи с цитатой и пометкой КРИТИЧНО);
живость русского (канцелярит, кальки, ритм, естественность); цельность и логика подачи.
Итоговый балл каждому, ранжирование, 2-3 предложения на вариант.
В САМОМ КОНЦЕ отдельной строкой: ПОБЕДИТЕЛЬ: <A|B|C>""",
}


def call_judge(prompt):
    last = None
    for model in JUDGES:
        for a in range(2):
            if a:
                time.sleep(10)
            try:
                if model.startswith('openai:'):
                    text, _ = _openai_stream([{'role': 'user', 'content': prompt}], model[7:], 8000)
                else:
                    msg = gp._raw_stream([{'role': 'user', 'content': prompt}], model, 8000,
                                         thinking=False, effort=None)
                    text = ''.join(b.text for b in msg.content if b.type == 'text')
                if text.strip():
                    return text.strip(), model
                last = f'{model}: пусто'
            except Exception as e:
                last = f'{model}: {repr(e)[:90]}'
            print(f'  ретрай: {last}', file=sys.stderr, flush=True)
    raise RuntimeError(f'судьи исчерпаны: {last}')


def main():
    report = ['# Аудит модельных версий волны 1 (слепое ранжирование A/B/C)\n',
              'A = клод (haiku+opus), B = gemini-3.1-pro, C = gpt-5.6-terra. '
              'Судье маппинг не сообщался.\n']
    wins = {}   # (slug, lens) -> (winner, judge)
    for job in JOBS:
        slug = job['slug']
        arts = []
        for label, sfx in VARIANTS:
            body = open(os.path.join(DIR, f'gp-{slug}{sfx}.html'), encoding='utf-8').read()
            arts.append(f'===== ВАРИАНТ {label} =====\n{body}')
        pack = '\n\n'.join(arts)
        for lens, persona in LENSES.items():
            head = persona.format(donor=job['donor'], donor_note=job['donor_note'])
            print(f'== {slug} / {lens}', flush=True)
            out, judge = call_judge(head + '\n\n' + pack)
            m = re.search(r'ПОБЕДИТЕЛЬ:\s*([ABC])', out)
            w = m.group(1) if m else '?'
            wins[(slug, lens)] = (w, judge)
            report.append(f'\n\n## {slug} / линза {lens} (судья: {judge}, победитель: {w})\n\n{out}')
            print(f'   победитель: {w} (судья {judge})', flush=True)
    # сводка
    names = {'A': 'клод', 'B': 'gemini', 'C': 'gpt', '?': '?'}
    tally = {}
    lines = ['\n\n# Сводка победителей\n', '| Тема | SEO | Донор | Качество |', '|---|---|---|---|']
    for job in JOBS:
        row = [job['slug']]
        for lens in ('seo', 'donor', 'quality'):
            w, _ = wins.get((job['slug'], lens), ('?', ''))
            row.append(names[w])
            tally[names[w]] = tally.get(names[w], 0) + 1
        lines.append('| ' + ' | '.join(row) + ' |')
    lines.append('\nИтого побед: ' + ', '.join(f'{k}: {v}' for k, v in
                 sorted(tally.items(), key=lambda kv: -kv[1])))
    report[1:1] = lines   # сводку - в начало, после шапки
    open(os.path.join(DIR, 'audit-models-report.md'), 'w', encoding='utf-8').write('\n'.join(report))
    print('=> audit-models-report.md')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
