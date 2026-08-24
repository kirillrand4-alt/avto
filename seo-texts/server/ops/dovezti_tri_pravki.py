# -*- coding: utf-8 -*-
"""Довезти три правки, которых нет на сервере: адрес ответившего и ящик сбоя.

Проверка меток 24.08 показала, что на боевой машине нет:
  * store.mark_failed(..., mailbox_id=) — сбой отправки не запоминает,
    с какого ящика не ушло; разбирать отказы по ящикам нечем;
  * leaddesk.push_warm_lead(..., otvetil=) — лид показывает приёмную, а
    не человека, который реально ответил;
  * imap_watcher._lid(...) — адрес ответившего не доезжает до лида.

Последние две горят: за 24.08 уже два ответа, и оба легли в ленту с
адресом приёмной.

Каталог C:\\sender\\sender делят несколько сессий, поэтому целиком файлы
НЕ заливаем: правим по якорям в серверном тексте. Каждый якорь обязан
встретиться ровно один раз — иначе правка не применяется вовсе. Порядок
жёсткий: .bak, запись, py_compile; сбой на любом файле откатывает ВСЕ
три, чтобы не оставить машину в половинчатом состоянии.

    python zapusk_svoego_skripta.py ops/dovezti_tri_pravki.py          # вхолостую
    python zapusk_svoego_skripta.py ops/dovezti_tri_pravki.py primenit # применить
"""
import io
import os
import py_compile
import sys
import time

КОРЕНЬ = r"C:\sender\sender"
ПРИМЕНИТЬ = "primenit" in sys.argv[1:]


def _прочесть(имя):
    return io.open(os.path.join(КОРЕНЬ, имя), encoding="utf-8").read()


# ---------------------------------------------------------------- store.py #

def правка_store(т):
    сиг = ("    def mark_failed(self, message_id: int, error: str, "
           "*, retryable: bool) -> None:")
    if т.count(сиг) != 1:
        return None, "сигнатура mark_failed найдена %d раз" % т.count(сиг)
    if "Optional" not in т:
        return None, "в файле нет Optional — некуда типизировать параметр"
    нов_сиг = ("    def mark_failed(self, message_id: int, error: str, "
               "*, retryable: bool,\n"
               "                    mailbox_id: Optional[str] = None) -> None:")
    т = т.replace(сиг, нов_сиг, 1)
    и = т.index(нов_сиг)
    строка_with = "        with self.transaction() as conn:\n"
    j = т.find(строка_with, и)
    if j < 0:
        return None, "внутри mark_failed нет транзакции — якорь не тот"
    блок = (
        '        # ЯЩИК СБОЯ. Раньше не писался вовсе: у 42 отказов из 43\n'
        '        # (замер 21.08) колонка пустая, и разобрать отказы по ящикам\n'
        '        # было нечем. Пишем, только когда ящик известен — чужое\n'
        '        # значение не затираем.\n'
        '        _ящик = str(mailbox_id).strip() if mailbox_id else ""\n'
        + строка_with +
        '            if _ящик:\n'
        '                conn.execute(\n'
        '                    "UPDATE messages SET mailbox_id=? WHERE id=?",\n'
        '                    (_ящик, message_id))\n'
    )
    т = т[:j] + блок + т[j + len(строка_with):]
    return т, None


# ------------------------------------------------------------- leaddesk.py #

def правка_leaddesk(т):
    сиг = ("    def push_warm_lead(self, recipient: Any, thread_id: str, "
           "snippet: str) -> Optional[int]:")
    if т.count(сиг) != 1:
        return None, "сигнатура push_warm_lead найдена %d раз" % т.count(сиг)
    нов_сиг = ("    def push_warm_lead(self, recipient: Any, thread_id: str, "
               "snippet: str,\n"
               "                       *, otvetil: Optional[str] = None"
               ") -> Optional[int]:")
    т = т.replace(сиг, нов_сиг, 1)
    и = т.index(нов_сиг)
    стар = '        email = getattr(recipient, "email", None)\n'
    j = т.find(стар, и)
    if j < 0:
        return None, "внутри push_warm_lead нет строки с email"
    нов = (
        '        # АДРЕС ОТВЕТИВШЕГО, А НЕ ТОТ, НА КОТОРЫЙ ПИСАЛИ. Письмо\n'
        '        # уходит на приёмную, там его пересылают внутрь, и отвечает\n'
        '        # человек со своего адреса. 21.08 так ответил зам. директора\n'
        '        # «Агропродукта»: писали на office@, ответил vs@ и прямо\n'
        '        # попросил присылать предложения ему — а в карточке стоял\n'
        '        # office@, и продавец ответил бы в приёмную. Связь с\n'
        '        # компанией держат recipient_id и ИНН, они не меняются.\n'
        '        email = str(otvetil or "").strip() or getattr('
        'recipient, "email", None)\n'
    )
    т = т[:j] + нов + т[j + len(стар):]
    return т, None


# --------------------------------------------------------- imap_watcher.py #

def правка_imap(т):
    пары = [
        ("                        self._reply_desk.push_warm_lead(\n"
         "                            recipient, ev.thread_id,\n"
         "                            f\"{метка} {ev.snippet or ''}\"[:900])",
         "                        self._lid(recipient, ev.thread_id,\n"
         "                                  f\"{метка} {ev.snippet or ''}\"[:900],\n"
         "                                  getattr(ev, \"from_addr\", None))"),
        ("                self._reply_desk.push_warm_lead("
         "recipient, ev.thread_id, snippet)",
         "                self._lid(recipient, ev.thread_id, snippet,\n"
         "                          getattr(ev, \"from_addr\", None))"),
    ]
    for стар, нов in пары:
        if т.count(стар) != 1:
            return None, "вызов лид-деска найден %d раз: %r" % (
                т.count(стар), стар[:60])
        т = т.replace(стар, нов, 1)

    якорь = "    def _ot_mayaka(self, from_addr: str) -> bool:"
    if т.count(якорь) != 1:
        return None, "якорь _ot_mayaka найден %d раз" % т.count(якорь)
    метод = (
        '    def _lid(self, recipient, thread_id, snippet, otvetil) -> None:\n'
        '        """Завести лид, передав адрес ответившего, но не ломаясь о\n'
        '        старую реализацию лид-деска, которая такого параметра не знает.\n'
        '\n'
        '        Адрес ответившего важен: письмо уходит на приёмную, там его\n'
        '        пересылают внутрь, и отвечает человек со своего адреса —\n'
        '        карточка должна показывать ЕГО, иначе продавец ответит в\n'
        '        приёмную.\n'
        '        """\n'
        '        try:\n'
        '            self._reply_desk.push_warm_lead(recipient, thread_id,\n'
        '                                            snippet, otvetil=otvetil)\n'
        '        except TypeError:\n'
        '            self._reply_desk.push_warm_lead(recipient, thread_id,\n'
        '                                            snippet)\n'
        '\n'
    )
    т = т.replace(якорь, метод + якорь, 1)
    return т, None


# store.py ИЗ СПИСКА УБРАН: правка там уже есть. Проверка меток соврала —
# искала буквальное «mailbox_id=None», а в коде «mailbox_id: Optional[str]
# = None», с пробелами и типом. Серверные строки 1455-1470 содержат и новую
# сигнатуру, и запись ящика. Функция правка_store оставлена на случай, если
# правку когда-нибудь затрёт выкаткой соседа.
ПРАВКИ = [("leaddesk.py", правка_leaddesk),
          ("imap_watcher.py", правка_imap)]

готово, беда = {}, []
for имя, функция in ПРАВКИ:
    try:
        текст = _прочесть(имя)
    except Exception as e:                                     # noqa: BLE001
        беда.append("%s: не прочитан (%s)" % (имя, str(e)[:60]))
        continue
    новый, ошибка = функция(текст)
    if ошибка:
        беда.append("%s: %s" % (имя, ошибка))
        continue
    готово[имя] = новый
    print("%-18s якоря найдены, станет %d байт (было %d)"
          % (имя, len(новый.encode("utf-8")), len(текст.encode("utf-8"))))

if беда:
    print("\nНЕ ПРИМЕНЯЮ — есть незакрытые вопросы:")
    for с in беда:
        print("  " + с)
    raise SystemExit(1)

if not ПРИМЕНИТЬ:
    print("\nвхолостую: все якоря на месте, ничего не записано.")
    print("для записи: zapusk_svoego_skripta.py ops/dovezti_tri_pravki.py primenit")
    raise SystemExit(0)

метка = int(time.time())
копии = {}
try:
    for имя, новый in готово.items():
        путь = os.path.join(КОРЕНЬ, имя)
        копия = путь + ".bak-%d" % метка
        io.open(копия, "w", encoding="utf-8").write(_прочесть(имя))
        копии[имя] = копия
        io.open(путь, "w", encoding="utf-8").write(новый)
        py_compile.compile(путь, doraise=True)
        print("%-18s записан и компилируется, копия %s"
              % (имя, os.path.basename(копия)))
except Exception as e:                                         # noqa: BLE001
    print("\nСБОЙ: %s — откатываю ВСЕ файлы" % str(e)[:140])
    for имя, копия in копии.items():
        try:
            io.open(os.path.join(КОРЕНЬ, имя), "w",
                    encoding="utf-8").write(io.open(копия, encoding="utf-8").read())
            print("  откачен %s" % имя)
        except Exception as e2:                                # noqa: BLE001
            print("  НЕ ОТКАЧЕН %s: %s" % (имя, str(e2)[:80]))
    raise SystemExit(2)

print("\nвсе три правки на месте. Панель подхватит их после перезапуска "
      "службы — это действие владельца: Restart-Service SenderPanel -Force")
