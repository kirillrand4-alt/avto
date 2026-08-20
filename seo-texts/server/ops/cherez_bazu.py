# -*- coding: utf-8 -*-
"""Запустить любой мой ops-скрипт через ВТОРОЙ шлюз (baza-ai).

gen_provider читает адрес и ключ из окружения, а окружение перекрывает
.env — значит переключить шлюз можно, ничего в самом клиенте не трогая.

Ключ лежит на сервере в C:\\sender\\baza.key и в репозиторий не попадает.

Оговорка про двери. У baza-ai работает только OpenAI-совместимая
/v1/chat/completions; Anthropic-совместимая /v1/messages отвечает 404.
gen_provider выбирает дверь по имени модели, поэтому через этот шлюз
сейчас ходят gpt/gemini/deepseek и прочие «чужие», а claude-* уйдёт в
несуществующую дверь. Клодовские модели там есть, но чтобы их звать,
клиенту нужна отдельная правка.

    python cherez_bazu.py <скрипт.py> [аргументы...]
"""
import io
import os
import runpy
import sys

КЛЮЧ = r"C:\sender\baza.key"
if not os.path.exists(КЛЮЧ):
    print(f"нет ключа {КЛЮЧ}")
    raise SystemExit(2)
os.environ["PROVIDER_API_KEY"] = io.open(КЛЮЧ, encoding="utf-8").read().strip()
os.environ["PROVIDER_BASE_URL"] = os.environ.get("BAZA_URL",
                                                 "https://api.baza-ai.org")
print(f"шлюз: {os.environ['PROVIDER_BASE_URL']}")

скрипт = sys.argv[1]
if not os.path.isabs(скрипт):
    скрипт = os.path.join(r"C:\sender\_ops", os.path.basename(скрипт))
sys.argv = [скрипт] + sys.argv[2:]
runpy.run_path(скрипт, run_name="__main__")
