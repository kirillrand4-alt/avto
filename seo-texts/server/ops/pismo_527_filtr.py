# -*- coding: utf-8 -*-
"""Что видит фильтр очереди на #527: ту же строку, что и API, а не мою.

Прошлый замер звал letter_division() на строке, которую я собрал сам из
базы - с темой и телом. Функция ответила 'meyer', и по этой логике письмо не
должно показываться под фильтром «КЦ». Владелец видит обратное, значит
строка у API другая: список очереди мог не тащить тело письма, а без текста
лексика молчит и фильтр падает на метку карточки ('kc').

Берём строки ТЕМ ЖЕ вызовом, что и API, и печатаем: какие ключи в строке,
что вернёт letter_division на ней, и попадёт ли #527 под фильтр 'kc'.

    python zapusk_svoego_skripta.py ops/pismo_527_filtr.py 527
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.confirm import ConfirmSend                          # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.suppression import Suppression                      # noqa: E402

ID = int(sys.argv[1]) if len(sys.argv) > 1 else 527

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))

# Тот же источник строк, что у API очереди.
строки = store.confirm_list(limit=100000)
print(f"строки взяты через store.confirm_list: {len(строки)}")

if not строки:
    print("не нашли, чем API берёт очередь")
    raise SystemExit(0)

наша = None
for r in строки:
    if int((r or {}).get("id") or 0) == ID:
        наша = r
        break
if наша is None:
    print(f"#{ID} в выдаче очереди нет")
    raise SystemExit(0)

print(f"\nключи строки #{ID}: {sorted(наша.keys())}")
for k in ("subject", "body"):
    v = наша.get(k)
    print(f"  {k}: {'нет ключа' if k not in наша else (str(v)[:60] + ' …' if v else 'ПУСТО')}")
panel = наша.get("panel") if isinstance(наша.get("panel"), dict) else {}
print(f"  panel есть: {bool(panel)} | letter внутри panel: "
      f"{isinstance(panel.get('letter'), dict)}")

d = cs.letter_division(наша)
print(f"\nletter_division(строка API) -> {d!r}")
comp = panel.get("company") if isinstance(panel.get("company"), dict) else {}
запас = str(comp.get("division") or "")
итог = (str(d or "") or запас).lower()
print(f"запасной источник (карточка) = {запас!r}")
print(f"фильтр 'kc':    показать = {(not итог) or ('kc' in итог)}")
print(f"фильтр 'meyer': показать = {(not итог) or ('meyer' in итог)}")
