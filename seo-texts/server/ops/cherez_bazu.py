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
# ДВЕРЬ ОДНА. /v1/messages у baza-ai отвечает 404, клодовские модели там
# ходят по OpenAI-совместимой. Переключатель живёт в gen_provider.
os.environ["PROVIDER_OPENAI_ONLY"] = "1"
print(f"шлюз: {os.environ['PROVIDER_BASE_URL']} (дверь одна, OpenAI)")


def _пул():
    """Остаток пула токенов — чтобы замерить расход прогона."""
    import json
    import urllib.request
    зпр = urllib.request.Request(
        os.environ["PROVIDER_BASE_URL"].rstrip("/") + "/v1/usage",
        headers={"authorization": "Bearer " + os.environ["PROVIDER_API_KEY"],
                 "User-Agent": "curl/8.5.0"})
    with urllib.request.urlopen(зпр, timeout=60) as о:
        return int(json.loads(о.read())["used_tokens"])


_до = None
try:
    _до = _пул()
    print(f"пул израсходовано до: {_до}")
except Exception as ex:                                          # noqa: BLE001
    print("пул не прочесть:", str(ex)[:90])

скрипт = sys.argv[1]
if not os.path.isabs(скрипт):
    скрипт = os.path.join(r"C:\sender\_ops", os.path.basename(скрипт))
sys.argv = [скрипт] + sys.argv[2:]
try:
    runpy.run_path(скрипт, run_name="__main__")
finally:
    if _до is not None:
        try:
            _после = _пул()
            print(f"\nПУЛ: было {_до}, стало {_после}, "
                  f"израсходовано за прогон {_после - _до} токенов "
                  f"(= ${(_после - _до) * 7.5 / 1_000_000:.2f} по цене "
                  f"$75 за 10 млн)")
        except Exception as ex:                                  # noqa: BLE001
            print("пул после не прочесть:", str(ex)[:90])
