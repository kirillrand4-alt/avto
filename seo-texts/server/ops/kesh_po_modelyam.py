# -*- coding: utf-8 -*-
"""Читается ли кэш на КАЖДОЙ модели: sonnet против opus, по четыре вызова.

Две проверки уже сделаны и обе сняли подозрение:
  * шлюз читает кэш — на sonnet-4-6 второй и третий вызовы с одинаковым
    system дали чтение 51592 и ускорение с 24.5 до 3.5 секунды;
  * промпт не течёт — статика gen_prompt у трёх разных компаний совпала
    байт в байт, хеш 8227d0c87a488b51 на 34955 знаках.
А в журнале партии каждое письмо пишет кэш на каждом из пяти вызовов и
не читает ни разу. Разница между замером и боем ровно одна: мерили на
sonnet, письма пишет opus.

Догадка: шлюз раскидывает вызовы по нескольким апстримам, а кэш живёт на
конкретном. Тогда у редкой модели попадания случаются, у нагруженной —
нет. Проверяем прямо: одинаковый system, по четыре вызова на модель.

Если чтения нет — вывод практический: писать кэш ДОРОЖЕ, чем не писать
(запись 1.25 ставки против обычного входа 1.0), и надо звать
_raw_stream с cache_system=False.
"""
import sys
import time

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")
import gen_provider                                            # noqa: E402

СИСТЕМА = ("Ты помощник, который отвечает одним словом.\n"
           + ("Это неизменяемая часть промпта для проверки кэша шлюза. "
              "Она одинакова во всех вызовах байт в байт.\n") * 400)
ЗАПРОС = [{"role": "user", "content": "Ответь одним словом: готов"}]

print("длина системного блока: %d знаков\n" % len(СИСТЕМА))
for модель in ("claude-sonnet-4-6", "claude-opus-4-8"):
    print("=== %s ===" % модель)
    записей = чтений = 0
    for н in range(1, 5):
        т0 = time.time()
        try:
            m = gen_provider._raw_stream(ЗАПРОС, модель, 32, thinking=False,
                                         system=СИСТЕМА)
            u = getattr(m, "usage", None)
            зап = int(getattr(u, "cache_creation_input_tokens", 0) or 0)
            чт = int(getattr(u, "cache_read_input_tokens", 0) or 0)
            записей += 1 if зап else 0
            чтений += 1 if чт else 0
            print("  вызов %d: %5.1f c | вход=%s запись=%d чтение=%d"
                  % (н, time.time() - т0,
                     getattr(u, "input_tokens", "?"), зап, чт))
        except Exception as e:                                 # noqa: BLE001
            print("  вызов %d: СБОЙ %5.1f c %s: %s"
                  % (н, time.time() - т0, type(e).__name__, str(e)[:120]))
        time.sleep(1)
    print("  итог: вызовов с записью %d, с чтением %d\n" % (записей, чтений))

print("=== ТО ЖЕ БЕЗ КЭША (cache_system=False) НА OPUS ===")
for н in (1, 2):
    т0 = time.time()
    try:
        m = gen_provider._raw_stream(ЗАПРОС, "claude-opus-4-8", 32,
                                     thinking=False, system=СИСТЕМА,
                                     cache_system=False)
        u = getattr(m, "usage", None)
        print("  вызов %d: %5.1f c | вход=%s запись=%s чтение=%s"
              % (н, time.time() - т0,
                 getattr(u, "input_tokens", "?"),
                 getattr(u, "cache_creation_input_tokens", "?"),
                 getattr(u, "cache_read_input_tokens", "?")))
    except Exception as e:                                     # noqa: BLE001
        print("  вызов %d: СБОЙ %5.1f c %s: %s"
              % (н, time.time() - т0, type(e).__name__, str(e)[:120]))
    time.sleep(1)
