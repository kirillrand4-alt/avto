# -*- coding: utf-8 -*-
"""Хирургически внести в серверные dsn.py и imap_watcher.py заслон от
ложных отбивок. Бэкап .bak, проверка результата, откат при неудаче.

Не перезаписываем файл целиком: C:\\sender\\sender\\ общий с соседней
сессией, и целая копия затёрла бы её правки.
"""
import hashlib
import io
import shutil
import sys

писать = len(sys.argv) > 1 and sys.argv[1] == "primenit"

ДСН = r"C:\sender\sender\dsn.py"
ВОЧ = r"C:\sender\sender\imap_watcher.py"

СТАРОЕ_LOOKS = '''def looks_like_dsn(msg: EmailMessage, subject: str, body: str) -> bool:
    """Похоже ли письмо на отчёт о недоставке (по типу, теме, отправителю)."""
    ctype = msg.get_content_type()
    if ctype in ("multipart/report", "message/delivery-status"):
        return True
    if any(p.get_content_type() == "message/delivery-status"
           for p in msg.walk()) if msg.is_multipart() else False:
        return True
    from_addr = (msg.get("From", "") or "").lower()
    if any(f"{loc}@" in from_addr for loc in ("mailer-daemon", "postmaster")):
        return True
    text = f"{subject} {body}".lower()
    return any(m in text for m in _DSN_SUBJECT_MARKERS)
'''

НОВОЕ_LOOKS = '''def dsn_po_strukture(msg: EmailMessage) -> bool:
    """УЛИКА отчёта в структуре письма, а не в словах и не в отправителе.

    Настоящий отчёт о недоставке всегда несёт машинную часть: сам тип
    multipart/report либо вложенную message/delivery-status. По ней отчёт
    отличается от чего угодно другого, что пришло с адреса postmaster@.
    """
    if msg.get_content_type() in ("multipart/report", "message/delivery-status"):
        return True
    if msg.is_multipart():
        return any(p.get_content_type() == "message/delivery-status"
                   for p in msg.walk())
    return False


def looks_like_dsn(msg: EmailMessage, subject: str, body: str) -> bool:
    """Похоже ли письмо на отчёт о недоставке (по типу, теме, отправителю).

    ЭТО ПРЕДПОЛОЖЕНИЕ, А НЕ ПРИГОВОР. Два последних признака - отправитель
    postmaster@ и слова в теме - дают ложные срабатывания: с postmaster@
    приходят ещё и агрегированные отчёты DMARC, которые о недоставке не
    говорят ничего. Решает вызывающий: у него после parse_dsn есть данные
    (адреса, код, статус), и пустой разбор без улики в структуре отбивкой
    считать нельзя.
    """
    if dsn_po_strukture(msg):
        return True
    from_addr = (msg.get("From", "") or "").lower()
    if any(f"{loc}@" in from_addr for loc in ("mailer-daemon", "postmaster")):
        return True
    text = f"{subject} {body}".lower()
    return any(m in text for m in _DSN_SUBJECT_MARKERS)
'''

СТАРОЕ_STATUS = '''        m = _RE_STATUS.search(text)
        status = m.group(1) if m else None
'''
НОВОЕ_STATUS = '''        m = _RE_STATUS.search(text)
        status = m.group(1) if m else None
        if not status:
            # МИНИМАЛЬНЫЙ ОТЧЁТ КЛАДЁТ СТАТУС ЗАГОЛОВКОМ ВЕРХНЕГО УРОВНЯ.
            # Простые шлюзы шлют не multipart/report, а обычное письмо с
            # «Status: 5.1.1» в шапке; _collect_text берёт тела частей, и
            # такой статус терялся целиком - отчёт получал вердикт по одним
            # словам. Читаем и его: это единственная машинная улика,
            # отличающая такой отчёт от письма, просто похожего на отчёт.
            заголовок = str(msg.get("Status", "") or "").strip()
            if re.fullmatch(r"[245]\\.\\d{1,3}\\.\\d{1,3}", заголовок):
                status = заголовок
'''

СТАРОЕ_IMP = '''    from sender.dsn import looks_like_dsn, parse_dsn  # type: ignore
except Exception:  # noqa: BLE001
    looks_like_dsn = None
    parse_dsn = None'''
НОВОЕ_IMP = '''    from sender.dsn import (dsn_po_strukture, looks_like_dsn,  # type: ignore
                            parse_dsn)
except Exception:  # noqa: BLE001
    looks_like_dsn = None
    parse_dsn = None
    dsn_po_strukture = None'''

СТАРОЕ_РАЗБОР = '''            orig_to = list(info.orig_to)
            if not rfc_message_id and info.orig_message_id:
                rfc_message_id = info.orig_message_id
'''
НОВОЕ_РАЗБОР = '''            orig_to = list(info.orig_to)
            # ПУСТОЙ РАЗБОР БЕЗ УЛИКИ В СТРУКТУРЕ - НЕ ОТБИВКА.
            #
            # looks_like_dsn относит к отчётам всё, что пришло с адреса
            # postmaster@, и это ловит агрегированные отчёты DMARC: их шлёт
            # каждый крупный почтовик раз в сутки с того же адреса. 21.08
            # такой отчёт от snemaservis.ru про наш домен лёг в события как
            # bounce - при нулевой отправке за день панель показала отбивку.
            # Настоящий отчёт всегда даёт хоть что-то: адрес, код, статус или
            # машинную часть message/delivery-status. Нет ничего из этого -
            # письмо разбираем дальше обычным порядком, а не хороним в
            # счётчике недоставки.
            _пусто = not (failed_addrs or info.smtp_code or info.status)
            _улика = (dsn_po_strukture(msg)
                      if dsn_po_strukture is not None else True)
            if _пусто and not _улика:
                kind = ("complaint"
                        if self._is_complaint(msg, subject, body)
                        else "reply"
                        if self._is_reply(msg, in_reply_to, references)
                        else "other")
                dsn_detail, failed_addrs, orig_to = {}, [], []
            elif not rfc_message_id and info.orig_message_id:
                rfc_message_id = info.orig_message_id
'''

ЗАДАНИЕ = [(ДСН, [(СТАРОЕ_LOOKS, НОВОЕ_LOOKS), (СТАРОЕ_STATUS, НОВОЕ_STATUS)]),
           (ВОЧ, [(СТАРОЕ_IMP, НОВОЕ_IMP), (СТАРОЕ_РАЗБОР, НОВОЕ_РАЗБОР)])]

for путь, замены in ЗАДАНИЕ:
    т = io.open(путь, encoding="utf-8").read()
    print(f"\n{путь}: {len(т)} байт, sha "
          f"{hashlib.sha256(т.encode()).hexdigest()[:16]}")
    новый = т
    ладно = True
    for старое, новое in замены:
        if новое.strip().splitlines()[0] in новый and старое not in новый:
            print("  уже применено — пропускаю")
            continue
        if старое not in новый:
            print("  ЯКОРЬ НЕ НАЙДЕН — не трогаю файл")
            ладно = False
            break
        новый = новый.replace(старое, новое, 1)
    if not ладно or новый == т:
        continue
    print(f"  после правки: {len(новый)} байт "
          f"(+{len(новый) - len(т)})")
    if not писать:
        print("  сухой прогон")
        continue
    shutil.copyfile(путь, путь + ".bak")
    io.open(путь, "w", encoding="utf-8").write(новый)
    # проверка: файл должен разбираться питоном
    import ast
    try:
        ast.parse(io.open(путь, encoding="utf-8").read())
        print("  записано, синтаксис ок, бэкап .bak рядом")
    except Exception as ex:                                   # noqa: BLE001
        shutil.copyfile(путь + ".bak", путь)
        print(f"  СИНТАКСИС СЛОМАЛСЯ ({ex}) — ОТКАТИЛ из .bak")
