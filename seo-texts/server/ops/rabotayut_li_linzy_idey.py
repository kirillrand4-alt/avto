# -*- coding: utf-8 -*-
"""Работают ли линзы идей вообще — или молча падают по длине ответа.

call() считает провалом ответ короче 200 знаков (защита от обрезанного
стрима). Линза просит ДВЕ СТРОКИ идеи — это может быть и 120 знаков. Тогда
call() делает две попытки, бросает RuntimeError, ai_quota ловит его в
`except: continue` — и письмо остаётся без идей, а никто об этом не узнаёт.

Зовём настоящие линзы настоящим промптом и смотрим длину ответа.
"""
import sys

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                        # noqa: E402
from sender.ai_quota import AiQuota                              # noqa: E402

ctx = ("Компания: ООО «Восьмой Механический». ОКВЭД: 25.62. "
       "Деятельность: механическая обработка металла.")
линзы = dict(list(AiQuota._IDEA_LENSES_KC.items())[:3])
print(f"проверяю {len(линзы)} линз КЦ\n")

упало = 0
for имя, линза in линзы.items():
    промпт = (f"{линза}\n\n{ctx}\n\nОтветь 2 строками, по одной идее на "
              "строку, без нумерации.")
    try:
        msg = GP.call(None, [{"role": "user", "content": промпт}],
                      model="claude-haiku-4-5", attempts=2, thinking=False)
        т = "".join(b.text for b in msg.content
                    if getattr(b, "type", "") == "text").strip()
        print(f"  [{имя}] ОК, {len(т)} знаков: {т[:90]!r}")
    except Exception as ex:                                      # noqa: BLE001
        упало += 1
        хвост = str(ex)
        print(f"  [{имя}] УПАЛА: {хвост[:150]}")

print(f"\nупало линз: {упало} из {len(линзы)}")
if упало:
    print("=> письма пишутся без части идей, и никто об этом не узнаёт:")
    print("   ai_quota ловит это в `except Exception: continue`")
