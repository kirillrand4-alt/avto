# -*- coding: utf-8 -*-
"""Проверить, что линза идей ходит и рассуждения не просит.

Выкатка ai_quota пошла раньше правки gen_provider: если параметр не дошёл,
вызов падает TypeError и глохнет в except — линзы молча исчезают, а письма
теряют идеи. Зовём ровно так, как зовёт конвейер.
"""
import inspect
import sys

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                        # noqa: E402

п = inspect.signature(GP.call).parameters
print("параметры call():", list(п))
print("thinking есть:", "thinking" in п,
      "| умолчание:", п.get("thinking").default if "thinking" in п else "—")

if "thinking" not in п:
    print("ПЛОХО: линзы идей будут падать"); raise SystemExit(2)

msg = GP.call(None, [{"role": "user", "content":
                      "Назови одну причину, зачем заводу компрессор. "
                      "Ответь одной строкой."}],
              model="claude-haiku-4-5", attempts=2, thinking=False)
т = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
u = getattr(msg, "usage", None)
print(f"ответ ({len(т)} знаков): {т.strip()[:120]}")
print(f"вход {getattr(u,'input_tokens',0)} | выход {getattr(u,'output_tokens',0)}")
print("линза идей работает и рассуждения не просит")
