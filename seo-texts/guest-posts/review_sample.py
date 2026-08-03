# -*- coding: utf-8 -*-
"""Ревью опубликованного гост-поста (образец metall.life) четырьмя персонами через API."""
import sys, os
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen_provider as gp
from review_philolog import PERSONA as PHILOLOG
from review_engineer import PERSONA as ENGINEER

DIR = os.path.dirname(os.path.abspath(__file__))
TXT = open(os.path.join(DIR, 'sample-metall-life.txt'), encoding='utf-8').read()

LINKBUILDER = """Ты - опытный SEO-специалист по линкбилдингу и одновременно выпускающий редактор
отраслевого портала (принимаешь гост-посты). Оцени статью, опубликованную на стороннем сайте
metall.life со ссылкой на prokompressor.ru, по двум осям:
А) Как РЕДАКТОР ДОНОРА: взял бы такой материал? польза читателю, самодостаточность, не выглядит ли
рекламой, качество для площадки.
Б) Как ЛИНКБИЛДЕР АКЦЕПТОРА: якорь и его тип, положение ссылки, релевантность донор-акцептор,
риски (Минусинск/link spam), что улучшить в ссылочной механике.
Дай конкретные находки и в конце: 2 оценки по 10-балльной (донор/акцептор) + 3 главных улучшения."""

ANTIAI = """Ты - эксперт по детекции ИИ-текстов (стилометрия, паттерны LLM). Проанализируй статью:
ритм абзацев/предложений, канцелярит, мосты-связки, длинные тире, шаблонные конструкции, структурная
предсказуемость, признаки человеческой правки. Вердикт: похоже на ИИ / смешанное / человеческое,
с конкретными маркерами. В конце: 5 правил, как в будущих статьях уйти от найденных паттернов."""

PERSONAS = [('Филолог', PHILOLOG), ('Инженер', ENGINEER),
            ('Линкбилдер+редактор донора', LINKBUILDER), ('Анти-ИИ детектор', ANTIAI)]

def one(name, persona, client):
    prompt = persona + '\n\n=== СТАТЬЯ (опубликована на metall.life) ===\n' + TXT
    try:
        msg = gp.call(client, [{'role': 'user', 'content': prompt}], model='claude-fable-5')
        return name, ''.join(b.text for b in msg.content if b.type == 'text').strip()
    except Exception as e:
        return name, f'[сбой: {e!r}]'

def main():
    client = gp.make_client()
    res = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(one, n, p, client): n for n, p in PERSONAS}
        for f in as_completed(futs):
            n, out = f.result(); res[n] = out
            print('готово:', n, flush=True)
    parts = ['# Ревью образца гост-поста (metall.life, лазерная резка)\n']
    for n, _ in PERSONAS:
        parts.append(f'\n\n# {n}\n\n{res[n]}')
    open(os.path.join(DIR, 'review-sample-metall.md'), 'w', encoding='utf-8').write('\n'.join(parts))
    print('=> review-sample-metall.md')

if __name__ == '__main__':
    main()
