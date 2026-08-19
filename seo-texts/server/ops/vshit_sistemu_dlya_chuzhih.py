# -*- coding: utf-8 -*-
"""Отдавать системную часть и не-клодовским моделям + завести kimi/moonshot.

Две дыры, найденные при попытке замерить письма на gpt/gemini/deepseek:
  1. body['system'] ставился ТОЛЬКО в anthropic-ветке. У OpenAI-совместимой
     двери системная часть молча терялась — модель получала карточку фирмы
     без единого правила, без фактов и без формата ответа. Выглядит как
     «чужая модель не умеет писать письма», а на деле ей не сказали, что
     писать;
  2. kimi/moonshot не были в списке OpenAI-двери и уходили на /v1/messages,
     где шлюз отвечает 503 «нет канала».

Правим серверную копию точечно: она разошлась с моей и не совпадает ни с
одним коммитом. Идемпотентно, с .bak.
"""
import ast
import io
import shutil
import sys

ФАЙЛ = r"C:\sender\gen_provider.py"
СУХО = not ({"--катить", "--katit"} & set(sys.argv))

s = io.open(ФАЙЛ, encoding="utf-8").read()
было = len(s)

СТАРЫЙ_СПИСОК = ("        ('gpt', 'gemini', 'grok', 'deepseek', 'qwen', "
                 "'llama', 'kling', 'sora', 'veo'))")
НОВЫЙ_СПИСОК = ("        ('gpt', 'gemini', 'grok', 'deepseek', 'qwen', "
                "'llama', 'kling', 'sora',\n"
                "         'veo', 'kimi', 'moonshot', 'mistral', 'glm'))")

СТАРАЯ_ВЕТКА = """    else:
        # у OpenAI-совместимой двери свои имена: thinking/output_config там не
        # понимают, а usage без этой просьбы не приходит вовсе
        body['stream_options'] = {'include_usage': True}"""
НОВАЯ_ВЕТКА = """    else:
        # у OpenAI-совместимой двери свои имена: thinking/output_config там не
        # понимают, а usage без этой просьбы не приходит вовсе
        body['stream_options'] = {'include_usage': True}
        if system:
            # СИСТЕМНУЮ ЧАСТЬ ЗДЕСЬ ТОЖЕ НАДО ОТДАТЬ, а раньше она молча
            # ТЕРЯЛАСЬ: body['system'] ставился только в anthropic-ветке, и
            # у gpt/gemini/grok письмо уходило вообще без правил, фактов и
            # формата ответа. Выглядело это как «чужая модель не умеет
            # писать письма», хотя ей просто не сказали, что писать.
            # В OpenAI-совместимой двери роль называется 'system' и живёт
            # первым сообщением, а не отдельным полем.
            body['messages'] = ([{'role': 'system', 'content': system}]
                                + list(messages))"""

if "'kimi', 'moonshot'" in s and "role': 'system'" in s:
    print("правка уже вшита")
    raise SystemExit(0)

for имя, старое, новое in (("список моделей", СТАРЫЙ_СПИСОК, НОВЫЙ_СПИСОК),
                           ("ветка OpenAI", СТАРАЯ_ВЕТКА, НОВАЯ_ВЕТКА)):
    n = s.count(старое)
    print(f"{имя}: якорь найден {n} раз(а)")
    if n != 1:
        print(f"ОТМЕНА: якорь «{имя}» не единственный")
        raise SystemExit(2)
    s = s.replace(старое, новое, 1)

try:
    ast.parse(s)
except SyntaxError as ex:
    print("ОТМЕНА: не парсится:", ex)
    raise SystemExit(2)
print(f"парсится: да | было {было}, стало {len(s)}")

if СУХО:
    print("\nсухой прогон. Катить — --katit")
    raise SystemExit(0)

shutil.copy2(ФАЙЛ, ФАЙЛ + ".bak-system-openai")
io.open(ФАЙЛ, "w", encoding="utf-8", newline="").write(s)
print(f"ВШИТО. Резервная копия: {ФАЙЛ}.bak-system-openai")
