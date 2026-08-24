# -*- coding: utf-8 -*-
"""Принимает ли _lid пятый аргумент v_bitrix — иначе отказы молча теряются.

Соседняя сессия починила отказы: карточка заводится с пометкой [отказ] и
не уезжает в Битрикс. Зовёт она это через self._lid(..., v_bitrix=False),
а сам _lid выкатил я часом раньше — с четырьмя аргументами.

Вызов обёрнут в with suppress(Exception). Значит при несовпадении
сигнатур будет TypeError, исключение проглотится, и карточка НЕ
заведётся — а код при этом выглядит рабочим. Ровно тот случай, ради
которого две сессии и сверяются перед выкаткой.

Проверяем не глазами, а вызовом: собираем сигнатуру _lid и
push_warm_lead и пробуем позвать с v_bitrix на подставном лид-деске.
"""
import inspect
import sys

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

from sender.imap_watcher import ImapWatcher                    # noqa: E402
from sender.leaddesk import LeadDesk                           # noqa: E402

print("=== СИГНАТУРЫ ===")
for имя, объект in (("ImapWatcher._lid", getattr(ImapWatcher, "_lid", None)),
                    ("LeadDesk.push_warm_lead",
                     getattr(LeadDesk, "push_warm_lead", None))):
    if объект is None:
        print("  %-28s НЕТ ТАКОГО МЕТОДА" % имя)
        continue
    print("  %-28s %s" % (имя, inspect.signature(объект)))

принимает = False
try:
    п = inspect.signature(ImapWatcher._lid).parameters
    принимает = "v_bitrix" in п or any(
        з.kind == inspect.Parameter.VAR_KEYWORD for з in п.values())
except Exception as e:                                         # noqa: BLE001
    print("  сигнатуру не снять:", str(e)[:80])
print("\n_lid принимает v_bitrix: %s" % ("ДА" if принимает else "НЕТ"))

print("\n=== ПРОБА ВЫЗОВОМ ===")


class _Десk:
    def __init__(self):
        self.было = []

    def push_warm_lead(self, recipient, thread_id, snippet, **прочее):
        self.было.append((getattr(recipient, "email", "?"), thread_id,
                          snippet[:40], dict(прочее)))
        return 1


class _Кто:
    email = "proba@example.com"
    inn = "0000000000"


сторож = ImapWatcher.__new__(ImapWatcher)
сторож._reply_desk = _Десk()
try:
    сторож._lid(_Кто(), "t-1", "[отказ] проба", "otvetil@example.com",
                v_bitrix=False)
    print("  вызов с v_bitrix прошёл, лид заведён:",
          bool(сторож._reply_desk.было))
    for з in сторож._reply_desk.было:
        print("    %s" % (з,))
except TypeError as e:
    print("  TypeError: %s" % str(e)[:150])
    print("  ЗНАЧИТ отказы ТЕРЯЮТСЯ: вызов соседа падает, "
          "suppress глотает, карточки нет")
except Exception as e:                                         # noqa: BLE001
    print("  другая ошибка: %s: %s" % (type(e).__name__, str(e)[:120]))

print("\n=== ПРОБА БЕЗ v_bitrix (обычный путь ответа) ===")
сторож2 = ImapWatcher.__new__(ImapWatcher)
сторож2._reply_desk = _Десk()
try:
    сторож2._lid(_Кто(), "t-2", "[neutral] проба", "otvetil@example.com")
    print("  прошёл, лид заведён:", bool(сторож2._reply_desk.было))
except Exception as e:                                         # noqa: BLE001
    print("  %s: %s" % (type(e).__name__, str(e)[:120]))
