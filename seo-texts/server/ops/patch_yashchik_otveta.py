# -*- coding: utf-8 -*-
"""Ящик ветки в черновик ответа из карточки лида (api/app.py, lead_reply)."""
import io
import os
import py_compile
import time

ПУТЬ = r"C:\sender\sender\api\app.py"
ЗАМЕНЫ = [
 [
  "        # Вложения: пришли идентификаторы загруженных файлов — превращаем их в",
  "        # ЯЩИК ВЕТКИ. Ответ обязан уйти с того адреса, с которого клиент\n        # получил письмо: иначе на его «ответьте мне» отвечает незнакомый\n        # менеджер, и тред у клиента распадается на два. Черновики\n        # автоответчика ящик несут (reply_pipeline._panel кладёт ev.mailbox_id),\n        # а ответ из карточки лида — нет: панель здесь собиралась из трёх\n        # ключей, и выбор падал на _fallback_mailbox, то есть на любой\n        # свободный ящик направления. Владелец 28.08: «письмо для ответа в\n        # очередь ставится с рандомной почты что ли?». Берём ящик последней\n        # НАШЕЙ отправки этому получателю — это и есть ветка переписки.\n        with suppress(Exception):\n            _rid_vetki = getattr(lead, \"recipient_id\", None)\n            if _rid_vetki:\n                with deps.store._lock:\n                    _stroka = deps.store._conn.execute(\n                        \"SELECT mailbox_id FROM messages \"\n                        \" WHERE recipient_id = ? AND status = 'sent' \"\n                        \"   AND mailbox_id IS NOT NULL \"\n                        \" ORDER BY sent_at DESC LIMIT 1\",\n                        (int(_rid_vetki),)).fetchone()\n                if _stroka and _stroka[0]:\n                    panel[\"mailbox_id\"] = str(_stroka[0])\n\n        # Вложения: пришли идентификаторы загруженных файлов — превращаем их в"
 ]
]

т = io.open(ПУТЬ, encoding="utf-8").read()
if "_rid_vetki" in т:
    print("правка уже стоит")
    raise SystemExit(0)
for стар, нов in ЗАМЕНЫ:
    if т.count(стар) != 1:
        print("ЯКОРЬ НЕ ОДИН (%d)" % т.count(стар))
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
