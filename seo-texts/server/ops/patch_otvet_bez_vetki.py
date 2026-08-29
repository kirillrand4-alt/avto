# -*- coding: utf-8 -*-
"""Ответ новым письмом, без In-Reply-To, — тоже ответ."""
import io
import json
import os
import py_compile
import time

ПУТЬ = r"C:\sender\sender\imap_watcher.py"
МЕТКА = '_pisali_ranshe'
ЗАМЕНЫ = json.loads(r'''[["    def _extract_body(self, msg: EmailMessage) -> str:", "    # Машинные отправители: их «ответ» — уведомление робота, а не человек.\n    _МАШИНА = (\"noreply\", \"no-reply\", \"no_reply\", \"donotreply\", \"do-not-reply\",\n               \"mailer-daemon\", \"mailerdaemon\", \"postmaster@\", \"notification\",\n               \"notifications@\", \"notify@\", \"robot@\", \"bounce@\", \"abuse@\")\n\n    @classmethod\n    def _ot_mashiny(cls, from_addr: str) -> bool:\n        а = str(from_addr or \"\").strip().lower()\n        return bool(а) and any(п in а for п in cls._МАШИНА)\n\n    def _pisali_ranshe(self, recipient_id: int) -> bool:\n        \"\"\"Уходило ли этому получателю наше письмо. Ответ подразумевает письмо;\n        без этой проверки ответом станет любая рассылка компании из базы.\"\"\"\n        try:\n            store = self._store\n            with getattr(store, \"_lock\"):\n                строка = store._conn.execute(          # noqa: SLF001\n                    \"SELECT 1 FROM messages WHERE recipient_id = ? \"\n                    \"   AND sent_at IS NOT NULL LIMIT 1\",\n                    (int(recipient_id),)).fetchone()\n            return строка is not None\n        except Exception:  # noqa: BLE001 - сбой проверки не роняет приём письма\n            logger.exception(\"проверка «писали ли раньше» не сработала\")\n            return False\n\n    def _extract_body(self, msg: EmailMessage) -> str:"], ["        if kind == \"otchet\":\n            # Отчёт присылает ЧУЖОЙ почтовик про НАШ домен. Совпадение домена\n            # отправителя с карточкой получателя — совпадение, а не переписка.\n            recipient_id = None", "        if kind == \"otchet\":\n            # Отчёт присылает ЧУЖОЙ почтовик про НАШ домен. Совпадение домена\n            # отправителя с карточкой получателя — совпадение, а не переписка.\n            recipient_id = None\n        # ОТВЕТ БЕЗ ЗАГОЛОВКОВ ВЕТКИ. Ответом письмо считалось только по\n        # In-Reply-To/References, а половина деловой почты отвечает НОВЫМ\n        # письмом с новой темой: «компрессор КИП.», «Ооо ТЭКО». Такое письмо\n        # ложилось событием «входящее вне переписки» — ни ответа в сводке, ни\n        # карточки лида, ни отметки «этой компании уже ответили». Замер 29.08:\n        # среди 253 записей «вне переписки» 23 письма от живых людей, из них\n        # 11 привязаны к компании и просто не сочтены ответом.\n        #\n        # Признаём ответом, если сошлись ТРИ условия: письмо привязано к\n        # получателю, отправитель не машина и мы этому получателю ПИСАЛИ\n        # раньше. Без третьего условия ответом стала бы и рассылка компании,\n        # которой мы никогда не писали.\n        if (kind == \"other\" and recipient_id is not None\n                and not self._ot_mashiny(from_addr)\n                and self._pisali_ranshe(recipient_id)):\n            kind = \"reply\""]]''')

т = io.open(ПУТЬ, encoding="utf-8").read()
if МЕТКА in т:
    print("правка уже стоит")
    raise SystemExit(0)
for стар, нов in ЗАМЕНЫ:
    if т.count(стар) != 1:
        print("ЯКОРЬ НЕ ОДИН (%d): %r" % (т.count(стар), стар[:70]))
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
