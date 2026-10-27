# -*- coding: utf-8 -*-
"""Цитата прошлого письма под ответом в ветку (владелец 27.10: «да, применяй
первый вариант, я думал они будут видеть и так то что мы писали»). Веб-почта
сама кладёт под ответом «<дата>, <имя> написал(а): > …», панель — нет: «Северный
Технопарк» получил наше короткое «Re:» без исходного предложения и попросил
«продублируйте письмо». Теперь send_reply, если In-Reply-To — НАШЕ письмо (есть
в messages по rfc_message_id), кладёт под подписью его цитату. Ответ на письмо
клиента (его Message-ID у нас не хранится письмом) — без изменений.
Правка по якорю в sender.py: бэкап .bak-tsitata-<время>, py_compile, откат.
    tsitata_v_otvete.py [--primenit | --otkat] [--koren=<папка>]"""
import glob
import io
import os
import py_compile
import shutil
import sys
import time

КОРЕНЬ = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--koren=")), r"C:\sender\sender")
П = os.path.join(КОРЕНЬ, "sender.py")
БЫЛО = """        rendered = self._apply_signature(
            RenderedMessage(subject=subject, body=body), mailbox_id)
        mime_bytes = self._build_mime(headers, rendered, vlozheniya=vlozheniya)
        body = rendered.body   # в лог/события уходит то, что реально отправили"""
СТАЛО = """        rendered = self._apply_signature(
            RenderedMessage(subject=subject, body=body), mailbox_id)
        # ЦИТАТА-27.10 (владелец: «я думал, они будут видеть и так то, что мы
        # писали»). Веб-почта кладёт под ответом цитату прошлого письма, панель
        # не клала: напоминание «Re:» приходило без исходного предложения, и
        # клиент просил «продублируйте». Отвечаем на НАШЕ письмо (оно есть в
        # messages по Message-ID) — цитируем его под подписью; не нашли — как было.
        with suppress(Exception):
            from datetime import timedelta as _td
            _irt = _strip_crlf(in_reply_to or "").strip()
            _р = self.store._conn.execute(
                "SELECT body_rendered, sent_at, mailbox_id FROM messages "
                "WHERE rfc_message_id=? AND status='sent' LIMIT 1",
                (_irt,)).fetchone() if _irt else None
            if _р and (_р[0] or "").strip():
                _мб = self._mailbox_cfg(_р[2]) if _р[2] else None
                _имя = (getattr(_мб, "from_name", "") or _р[2] or "").strip()
                _имя_первое = (_имя.split() or [""])[0].lower()
                _жен = _имя_первое.endswith(("а", "я")) and _имя_первое not in (
                    "никита", "илья", "кузьма", "фома", "лука", "савва", "данила")
                try:
                    _когда = datetime.fromisoformat(str(_р[1])[:19]).replace(
                        tzinfo=timezone.utc).astimezone(timezone(_td(hours=3)))
                    _дата = _когда.strftime("%d.%m.%Y в %H:%M")
                except Exception:  # noqa: BLE001
                    _дата = str(_р[1] or "")[:10]
                _шапка = "%s, %s <%s> %s:" % (_дата, _имя, _р[2] or "",
                                              "написала" if _жен else "написал")
                _цитата = "\\n".join("> " + s for s in str(_р[0]).strip().splitlines())
                rendered = RenderedMessage(
                    subject=rendered.subject,
                    body=rendered.body.rstrip() + "\\n\\n\\n" + _шапка + "\\n" + _цитата + "\\n")
        mime_bytes = self._build_mime(headers, rendered, vlozheniya=vlozheniya)
        body = rendered.body   # в лог/события уходит то, что реально отправили"""
if "--otkat" in sys.argv:
    б = sorted(glob.glob(П + ".bak-tsitata-*"))
    if б:
        shutil.copy2(б[-1], П)
    print("=== ЦИТАТА: ОТКАТ (нужен рестарт) ===")
    sys.exit(0)
т = io.open(П, encoding="utf-8").read()
if "ЦИТАТА-27.10" in т:
    print("=== ЦИТАТА: УЖЕ БЫЛО ===")
    sys.exit(0)
if т.count(БЫЛО) != 1:
    print("якорь найден %d раз" % т.count(БЫЛО))
    print("=== ЦИТАТА: НЕ ПРИМЕНЕНО ===")
    sys.exit(0)
for нужно in ("suppress",):
    if нужно not in т.split("class ")[0]:
        print("в импортах sender.py нет", нужно)
        print("=== ЦИТАТА: НЕ ПРИМЕНЕНО ===")
        sys.exit(0)
т = т.replace(БЫЛО, СТАЛО)
if "--primenit" not in sys.argv:
    print("якорь на месте, сухой прогон. Применить — --primenit")
    sys.exit(0)
бэкап = П + ".bak-tsitata-%d" % int(time.time())
shutil.copy2(П, бэкап)
io.open(П, "w", encoding="utf-8").write(т)
try:
    py_compile.compile(П, doraise=True)
except Exception as е:  # noqa: BLE001
    shutil.copy2(бэкап, П)
    print("сбой, откат:", е)
    sys.exit(0)
print("бэкап:", бэкап)
print("=== ЦИТАТА: ПРИМЕНЕНО (нужен Restart-Service SenderPanel -Force) ===")
