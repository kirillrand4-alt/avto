# -*- coding: utf-8 -*-
"""auto_send: повтор Meyer по правилу владельца 13.10 не снимаем как «уже писали»
(~90 одобренных писем за 14.10). Правка по якорю, бэкап, py_compile, откат."""
import io
import py_compile
import shutil
import sys
import time
ПУТЬ = r"C:\\sender\\sender\\auto_send.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
if "ПОВТОР ОТ MEYER ПО ПРАВИЛУ ВЛАДЕЛЬЦА 13.10" in т:
    print("=== ПОВТОР В АВТООТПРАВКЕ: УЖЕ БЫЛО ===")
    sys.exit(0)
ПАРЫ = [('            _пр = str(review.get("reason") or "").lower()\n            _копия = ("копия на второй адрес" in _пр\n                      or "повтор разрешён" in _пр or "повтор разрешен" in _пр)\n            флаги = self.store.sent_flags(\n                emails=[почта] if почта else None,\n                inns=None if _копия else ([инн] if инн else None)) or {}\n            след = флаги.get(почта) or (\n                {} if _копия else (флаги.get(инн) or {}))\n            if след.get("ever"):\n                self.store.mark_skipped(\n', '            _пр = str(review.get("reason") or "").lower()\n            _копия = ("копия на второй адрес" in _пр\n                      or "повтор разрешён" in _пр or "повтор разрешен" in _пр)\n            # ПОВТОР ОТ MEYER ПО ПРАВИЛУ ВЛАДЕЛЬЦА 13.10 (после письма КЦ, или\n            # новый паспорт и прошло 30 дней; компания не отвечала). Очередь\n            # такое письмо пропускает (confirm._povtor_razreshen), а здесь оно\n            # снималось как «уже писали»: за 14.10 так ушло ~90 одобренных\n            # писем. Решаем тем же правилом по последней отправке на адрес\n            # или компанию; сработало — заслон «уже писали» не применяем.\n            if not _копия:\n                with suppress(Exception):\n                    _посл = self.store.last_contact(email=почта or None,\n                                                    inn=инн or None)\n                    if _посл:\n                        from sender.confirm import ConfirmSend\n                        if ConfirmSend(self.config, self.store)._povtor_razreshen(\n                                почта, _посл):\n                            _копия = None   # повтор разрешён: не проверяем вовсе\n            if _копия is None:\n                след = {}\n            else:\n                флаги = self.store.sent_flags(\n                    emails=[почта] if почта else None,\n                    inns=None if _копия else ([инн] if инн else None)) or {}\n                след = флаги.get(почта) or (\n                    {} if _копия else (флаги.get(инн) or {}))\n            if след.get("ever"):\n                self.store.mark_skipped(\n')]
for с, _н in ПАРЫ:
    if т.count(с) != 1:
        print("якорь (%d): %r" % (т.count(с), с[:120]))
        print("=== ПОВТОР В АВТООТПРАВКЕ: НЕ ПРИМЕНЕНО ===")
        sys.exit(0)
бэкап = ПУТЬ + ".bak-%d" % int(time.time())
shutil.copy2(ПУТЬ, бэкап)
for с, н in ПАРЫ:
    т = т.replace(с, н)
io.open(ПУТЬ, "w", encoding="utf-8").write(т)
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as е:  # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print("сбой, откат: %s" % е)
    print("=== ПОВТОР В АВТООТПРАВКЕ: ОТКАТ ===")
    sys.exit(0)
print("бэкап: %s" % бэкап)
print("=== ПОВТОР В АВТООТПРАВКЕ: ПРИМЕНЕНО ===")
