# -*- coding: utf-8 -*-
"""Включает ли маршрут шлюза рассуждение вопреки thinking=False.

Гейт адресата падал «срыв в рассуждение даже на low»: много токенов выхода,
текста почти нет. Один вызов в форме гейта — смотрим блоки ответа и токены.
"""
import sys
import time
sys.path.insert(0, r"C:\sender")
import gen_provider  # noqa: E402

ПРОМПТ = ("Оцени, может ли компания купить фотосепаратор или рентген-"
          "инспекцию. Компания: ООО «Агро», производство муки и круп, "
          "элеватор на 20 тыс. т. Ответь СТРОГО JSON: "
          '{"verdict":"верно|сомнительно|ошибка","pochemu":"…"}')
for модель in ("claude-sonnet-4-6", "claude-opus-4-8"):
    for усилие in ("low", None):
        t = time.time()
        try:
            m = gen_provider._raw_stream([{"role": "user", "content": ПРОМПТ}],
                                         модель, 2000, thinking=False,
                                         effort=усилие)
            блоки = [getattr(б, "type", "?") for б in m.content]
            текст = "".join(getattr(б, "text", "") or "" for б in m.content
                            if getattr(б, "type", "") == "text")
            дума = "".join(getattr(б, "thinking", "") or "" for б in m.content
                           if getattr(б, "type", "") == "thinking")
            u = m.usage
            print("%-18s усилие=%-5s %4.1f с | блоки %s | выход %s ток | текст %d зн "
                  "| рассуждение %d зн | stop=%s"
                  % (модель, усилие, time.time() - t, блоки,
                     getattr(u, "output_tokens", "?"), len(текст), len(дума),
                     m.stop_reason))
        except Exception as e:  # noqa: BLE001
            print("%-18s усилие=%-5s СБОЙ %s" % (модель, усилие, str(e)[:160]))
print("=== РАССУЖДАЕТ ЛИ ===")
