# -*- coding: utf-8 -*-
"""Сделать рассуждение параметром call() прямо в серверной копии.

Серверный gen_provider.py разошёлся с моим и не совпадает ни с одним
коммитом — это чья-то живая правка, перезаписывать целиком нельзя. Вносим
ровно два куска: параметр thinking в сигнатуру и снятие жёсткой константы
в теле.

СРОЧНОСТЬ. Выкаченный ai_quota уже зовёт call(..., thinking=False). Пока
серверный call этого не принимает, вызов падает TypeError и глохнет в
except — линзы идей молча перестают работать. Идемпотентно, с .bak.
"""
import ast
import io
import shutil
import sys

ФАЙЛ = r"C:\sender\gen_provider.py"
СУХО = not ({"--катить", "--katit"} & set(sys.argv))

s = io.open(ФАЙЛ, encoding="utf-8").read()
исходно = len(s)

СТАРАЯ_СИГ = ("def call(client, messages, model='claude-opus-4-8', "
              "attempts=8, effort=None):")
НОВАЯ_СИГ = ("def call(client, messages, model='claude-opus-4-8', "
             "attempts=8, effort=None,\n         thinking=True):")

СТАРОЕ_ТЕЛО = """    last = None
    ATTEMPTS = attempts
    thinking = True
"""
НОВОЕ_ТЕЛО = """    last = None
    ATTEMPTS = attempts
    # РАССУЖДЕНИЕ ТЕПЕРЬ ПАРАМЕТР, А НЕ КОНСТАНТА. Здесь стояло жёсткое
    # thinking=True, и каждый вызов через call() шёл с рассуждением, которого
    # никто не просил: по журналу шлюза такой вызов стоит $0.09-0.21 против
    # $0.02-0.05 с thinking={'type':'disabled'} — впятеро. Владелец заметил
    # это по своей панели: «раньше было без рассуждения».
    #
    # Умолчание оставляем True: через call() ходят чужие задачи (разбор
    # тендеров, классификация hh), и молча менять им поведение нельзя.
"""

if "thinking=True):" in s and "    thinking = True\n" not in s:
    print("правка уже вшита — ничего не делаю")
    raise SystemExit(0)

for имя, старое, новое in (("сигнатура", СТАРАЯ_СИГ, НОВАЯ_СИГ),
                           ("тело", СТАРОЕ_ТЕЛО, НОВОЕ_ТЕЛО)):
    n = s.count(старое)
    print(f"{имя}: якорь найден {n} раз(а)")
    if n != 1:
        print(f"ОТМЕНА: якорь «{имя}» не единственный")
        raise SystemExit(2)
    s = s.replace(старое, новое, 1)

if "thinking=thinking" not in s:
    print("ОТМЕНА: в call() нет проброса thinking=thinking в _raw_stream")
    raise SystemExit(2)
try:
    ast.parse(s)
except SyntaxError as ex:
    print("ОТМЕНА: после правки не парсится:", ex)
    raise SystemExit(2)
print(f"парсится: да | было {исходно} байт, стало {len(s)}")

if СУХО:
    print("\nсухой прогон: файл не тронут. Катить — --katit")
    raise SystemExit(0)

shutil.copy2(ФАЙЛ, ФАЙЛ + ".bak-thinking")
io.open(ФАЙЛ, "w", encoding="utf-8", newline="").write(s)
print(f"ВШИТО. Резервная копия: {ФАЙЛ}.bak-thinking")
