# -*- coding: utf-8 -*-
"""Карточка ручного ответа НОВОМУ адресату в ветке (владелец 23.10: «отправляй»
— письмо главному инженеру «АВТОТРАНСФОРМАТОР» Наумову, которого конструктор
Елясин поставил в копию). Штатный ConfirmSend.submit_reply (kind=reply, pending),
ящик ветки — panel.mailbox_id, In-Reply-To — письмо Елясина (тред у клиента
сохраняется). Отправка — потом otvet_cherez_pauzu.py <id> <ящик>.
Текст — файл UTF-8 на дропе (otvet-naumov.txt): 1-я строка тема, дальше тело."""
import os
import sys

import requests

sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.wiring import build_deps        # noqa: E402

# Параметры — аргументами (23.10: второй ответ, Тищенко / Серышевский комплекс);
# без аргументов — прежний случай (Наумов, АВТОТРАНСФОРМАТОР).
_а = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
КОМУ = _а.get("komu", "d.naumov@avtotransformator.ru")
ЯЩИК = _а.get("yashchik", "m.pavlov@kompressor-pro-expert.ru")
ИНН = _а.get("inn", "6321373742")
В_ОТВЕТ = _а.get("v_otvet", "<33c5cf6f438b41209c6c887f68253c9a@avtotransformator.ru>")
ФАЙЛ = _а.get("fayl", "otvet-naumov.txt")
ПОЛУЧ = _а.get("rid")
т = requests.get(os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/") + "/" + ФАЙЛ,
                 headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=60)
т.encoding = "utf-8"
тема, тело = т.text.split("\n", 1)
# Подпись ставит панель сама (send_reply: полная подпись менеджера). Своя в
# тексте давала две подписи подряд (23.10, ответы Наумову и Тищенко) — режем.
тело = тело.split("\n\nС уважением,")[0]
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = build_deps(cfg, st, dry_run=True).confirm
rid = (int(ПОЛУЧ),) if ПОЛУЧ else st._conn.execute(
    "SELECT id FROM recipients WHERE lower(email)='elyasin.m@avtotransformator.ru'").fetchone()
р = cs.submit_reply(reply_to=КОМУ, subject=тема.strip(), body=тело.strip(), in_reply_to=В_ОТВЕТ,
                    thread_id=None, recipient_id=rid[0] if rid else None, inn=ИНН,
                    panel={"mailbox_id": ЯЩИК, "vruchnuyu": "Claude по команде владельца 23.10"})
print("карточка:", р)
