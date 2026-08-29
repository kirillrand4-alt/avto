# -*- coding: utf-8 -*-
"""patch_otchyoty_watcher.py"""
import io
import json
import os
import py_compile
import time

ПУТЬ = r"C:\sender\sender\imap_watcher.py"
МЕТКА = "_eto_otchyot"
ЗАМЕНЫ = json.loads(r'''[["    def _extract_body(self, msg: EmailMessage) -> str:", "    # Агрегированный отчёт DMARC — не письмо и не событие про получателя.\n    # Его шлёт раз в сутки каждый крупный почтовик и КАЖДЫЙ домен, которому мы\n    # писали; тело — zip или xml. 28.08 в ленте таких оказалось 106 штук, ещё\n    # 48 записей были обломками их вложений, а один отчёт с noreply@el5-energo.ru\n    # привязался к карточке ПАО «ЭЛ5-Энерго» — по совпадению домена, будто\n    # компания нам написала.\n    _ОТЧЁТ_ТЕМА = re.compile(r\"^\\s*report[_ -]?domain\\s*:\", re.I)\n    _ОТЧЁТ_ОТПРАВИТЕЛЬ = (\"dmarc\", \"noreply-dmarc\", \"postmaster@\", \"dmarcreport\")\n    _ОТЧЁТ_ТИПЫ = (\"application/zip\", \"application/gzip\", \"application/x-gzip\",\n                   \"application/xml\", \"text/xml\")\n\n    @classmethod\n    def _eto_otchyot(cls, msg: EmailMessage, subject: str, from_addr: str) -> bool:\n        if cls._ОТЧЁТ_ТЕМА.match(str(subject or \"\")):\n            return True\n        от = str(from_addr or \"\").lower()\n        if any(п in от for п in cls._ОТЧЁТ_ОТПРАВИТЕЛЬ) and \"report\" in \\\n                str(subject or \"\").lower():\n            return True\n        тип = str(msg.get_content_type() or \"\").lower()\n        имя = str(msg.get_filename() or \"\")\n        return тип in cls._ОТЧЁТ_ТИПЫ and \"!\" in имя\n\n    def _extract_body(self, msg: EmailMessage) -> str:"], ["        else:\n            return v_tekst(self._decode_part(msg))\n        return \"\"", "        else:\n            # ОДНОЧАСТНОЕ НЕ-ТЕКСТОВОЕ письмо (zip-отчёт DMARC, счёт в pdf) —\n            # это вложение, а не текст. Раньше его байты уезжали в snippet и\n            # рисовались в ленте как «PK□□□□□CJ ]юд⊥пЙ□□□».\n            тип = str(msg.get_content_type() or \"\").lower()\n            if not тип.startswith(\"text/\"):\n                имя = str(msg.get_filename() or \"\").strip()\n                return \"[вложение %s%s]\" % (тип, (\", \" + имя) if имя else \"\")\n            return v_tekst(self._decode_part(msg))\n        return \"\""], ["        if self._ot_mayaka(from_addr):\n            kind = \"other\"\n        elif self._is_dsn(msg, subject, body):", "        if self._ot_mayaka(from_addr):\n            kind = \"other\"\n        elif self._eto_otchyot(msg, subject, from_addr):\n            kind = \"otchet\"\n        elif self._is_dsn(msg, subject, body):"], ["        if recipient_id is None and kind != \"dsn\":\n            recipient_id = self._recipient_by_telom(snippet)", "        if recipient_id is None and kind != \"dsn\":\n            recipient_id = self._recipient_by_telom(snippet)\n        if kind == \"otchet\":\n            # Отчёт присылает ЧУЖОЙ почтовик про НАШ домен. Совпадение домена\n            # отправителя с карточкой получателя — совпадение, а не переписка.\n            recipient_id = None"]]''')

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
