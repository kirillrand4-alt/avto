# -*- coding: utf-8 -*-
"""Привязка входящего по адресу в ТЕЛЕ письма (пересланная цитата)."""
import io
import os
import py_compile
import time

ПУТЬ = r"C:\sender\sender\imap_watcher.py"
ЗАМЕНЫ = [
 [
  "        if recipient_id is None and kind != \"dsn\":\n            recipient_id = self._recipient_by_svezhey_otpravkoy(from_addr)\n",
  "        if recipient_id is None and kind != \"dsn\":\n            recipient_id = self._recipient_by_svezhey_otpravkoy(from_addr)\n        # ПИСЬМО ПЕРЕСЛАЛИ КОЛЛЕГЕ, ОТВЕТИЛИ С ЛИЧНОГО ЯЩИКА. Ни отправитель,\n        # ни его домен нам ничего не говорят (mail.ru, gmail), зато в теле\n        # лежит цитата нашего письма с адресом получателя: «Кому:\n        # phlebolog-ufa@mail.ru». Владелец 28.08: из 182 входящих без\n        # привязки три оказались настоящими ответами клиентов, и все три\n        # опознаются по этому следу.\n        if recipient_id is None and kind != \"dsn\":\n            recipient_id = self._recipient_by_telom(snippet)\n"
 ],
 [
  "    def _recipient_by_svezhey_otpravkoy(self, from_addr: str) -> Optional[int]:",
  "    _АДРЕС_В_ТЕЛЕ = re.compile(r\"[A-Za-z0-9._%+\\-]+@[A-Za-z0-9.\\-]+\\.[A-Za-z]{2,}\")\n\n    def _recipient_by_telom(self, snippet: str) -> Optional[int]:\n        \"\"\"Получатель по адресу, найденному В ТЕКСТЕ письма (цитата нашего).\n\n        Берём только однозначный случай: в теле ровно ОДИН адрес, который\n        числится у нас получателем. Несколько разных — не гадаем: в цитате\n        может оказаться и наш адресат, и его подрядчик. Свои ящики\n        отбрасываем, иначе привяжемся к самим себе.\n        \"\"\"\n        текст = str(snippet or \"\")\n        if not текст:\n            return None\n        finder = getattr(self._store, \"find_recipient_by_email\", None)\n        if not callable(finder):\n            return None\n        свои = set()\n        try:\n            свои = {str(getattr(m, \"mailbox_id\", \"\")).strip().lower()\n                    for m in (self._config.mailboxes() or [])}\n        except Exception:  # noqa: BLE001 - без конфига просто не фильтруем\n            свои = set()\n        найдено: dict = {}\n        for адрес in self._АДРЕС_В_ТЕЛЕ.findall(текст)[:60]:\n            адрес = адрес.strip().lower()\n            if not адрес or адрес in свои or адрес in найдено:\n                continue\n            try:\n                строка = finder(адрес)\n            except Exception:  # noqa: BLE001 - сбой поиска не роняет приём\n                continue\n            if строка:\n                rid = строка.get(\"id\") if isinstance(строка, dict) else \\\n                    getattr(строка, \"id\", None)\n                if rid:\n                    найдено[адрес] = int(rid)\n        уникальные = set(найдено.values())\n        if len(уникальные) != 1:\n            if уникальные:\n                logger.info(\"привязка по телу пропущена: получателей в цитате %d\",\n                            len(уникальные))\n            return None\n        return уникальные.pop()\n\n    def _recipient_by_svezhey_otpravkoy(self, from_addr: str) -> Optional[int]:"
 ]
]

т = io.open(ПУТЬ, encoding="utf-8").read()
if "_recipient_by_telom" in т:
    print("правка уже стоит")
    raise SystemExit(0)
for стар, нов in ЗАМЕНЫ:
    if т.count(стар) != 1:
        print("ЯКОРЬ НЕ ОДИН (%d): %r" % (т.count(стар), стар[:60]))
        raise SystemExit(1)
было = т
for стар, нов in ЗАМЕНЫ:
    т = т.replace(стар, нов)
бэк = ПУТЬ + ".bak-%d" % int(time.time())
with io.open(бэк, "w", encoding="utf-8", newline="") as f:
    f.write(было); f.flush(); os.fsync(f.fileno())
with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
    f.write(т); f.flush(); os.fsync(f.fileno())
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as ex:
    with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
        f.write(было); f.flush(); os.fsync(f.fileno())
    print("НЕ КОМПИЛИРУЕТСЯ, откатил: %s" % ex)
    raise SystemExit(1)
print("готово: %d -> %d знаков, бэкап %s" % (len(было), len(т), os.path.basename(бэк)))
