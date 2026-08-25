# -*- coding: utf-8 -*-
"""Класть копию отправленного письма в папку «Отправленные» самого ящика.

ПОЧЕМУ ЭТО НУЖНО. SMTP доставляет письмо получателю и НИЧЕГО не оставляет у
отправителя: копию в «Отправленные» кладёт веб-интерфейс почтовика, когда
пишешь оттуда. Мы шлём мимо веб-интерфейса — значит в ящике нашего письма
нет вовсе.

СЛУЧАЙ 25.08.2026. Владелец: «когда я пишу ответ, этого ответа нету в
ящике», и в итоге зашёл в ящики руками. Замер живьём: у
v.melnikov@kompressor-air-expert.ru в «Отправленных» два письма, а по базе
с него за тот день ушло четырнадцать. Оператор отвечает клиенту и не видит
своего ответа там, где привык смотреть; клиент потом отвечает на письмо,
которого в ящике нет, и ветка в почтовике рвётся.

ИМЯ ПАПКИ НЕ УГАДЫВАЕМ. У Яндекса она приходит как
«&BB4EQgQ,BEAEMAQyBDsENQQ9BD0ESwQ1-» — это «Отправленные» в модифицированном
UTF-7, кодека для которого в стандартной библиотеке нет. Поэтому ищем по
флагу \\Sent из ответа LIST, и только если его нет — по знакомым именам.

НИКОГДА НЕ РОНЯЕТ ОТПРАВКУ. Письмо к этому мигу уже ушло; неудачная копия —
это неудобство, а не потеря. Все ошибки глушим здесь и возвращаем False.
"""
from __future__ import annotations

import base64
import imaplib
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_ЗНАКОМЫЕ = ("отправленные", "sent", "sent items", "sent messages")


def dekodirovat(imya: str) -> str:
    """Имя папки IMAP из модифицированного UTF-7 в обычную строку."""
    вых: list[str] = []
    буфер = ""
    внутри = False
    for сим in str(imya or ""):
        if внутри:
            if сим == "-":
                if буфер:
                    б = буфер.replace(",", "/")
                    б += "=" * ((4 - len(б) % 4) % 4)
                    try:
                        вых.append(base64.b64decode(б).decode("utf-16-be"))
                    except Exception:  # noqa: BLE001 - мусор оставляем как есть
                        вых.append("&" + буфер + "-")
                else:
                    вых.append("&")
                буфер, внутри = "", False
            else:
                буфер += сим
        elif сим == "&":
            внутри = True
        else:
            вых.append(сим)
    if внутри:                      # оборванная последовательность
        вых.append("&" + буфер)
    return "".join(вых)


def _razobrat_list(строка: Any) -> tuple[str, str]:
    """Строка ответа LIST -> (флаги, имя папки как его понимает сервер)."""
    т = строка.decode("utf-8", "replace") if isinstance(строка, bytes) else str(строка)
    м = re.match(r'^\((?P<фл>[^)]*)\)\s+(?:"[^"]*"|NIL)\s+(?P<имя>.+)$', т.strip())
    if not м:
        return "", ""
    имя = м.group("имя").strip()
    if имя.startswith('"') and имя.endswith('"'):
        имя = имя[1:-1]
    return м.group("фл").lower(), имя


def nayti_papku(imap: Any) -> Optional[str]:
    """Папка «Отправленные»: сперва по флагу \\Sent, потом по имени."""
    try:
        тип, данные = imap.list()
    except Exception:  # noqa: BLE001
        return None
    if тип != "OK" or not данные:
        return None
    по_имени = None
    for строка in данные:
        флаги, имя = _razobrat_list(строка)
        if not имя:
            continue
        if "\\sent" in флаги:
            return имя
        if по_имени is None and dekodirovat(имя).strip().lower() in _ЗНАКОМЫЕ:
            по_имени = имя
    return по_имени


def polozhit(mb_cfg: Any, mime_bytes: bytes, *, kogda: Optional[datetime] = None,
             timeout: float = 20.0, opener: Any = None) -> bool:
    """Положить письмо в «Отправленные» ящика. True — легло.

    opener нужен тестам: без него открываем настоящее IMAP4_SSL-соединение.
    """
    пароль = os.getenv(getattr(mb_cfg, "password_env", "") or "", "")
    if not пароль:
        logger.warning("копия в отправленные: нет пароля %s",
                       getattr(mb_cfg, "password_env", "?"))
        return False
    imap = None
    try:
        if opener is not None:
            imap = opener(mb_cfg)
        else:
            imap = imaplib.IMAP4_SSL(mb_cfg.imap_host, mb_cfg.imap_port,
                                     timeout=timeout)
            imap.login(mb_cfg.login, пароль)
        папка = nayti_papku(imap)
        if not папка:
            logger.warning("копия в отправленные: папка не найдена у %s",
                           getattr(mb_cfg, "mailbox_id", "?"))
            return False
        когда = kogda or datetime.now(timezone.utc)
        тип, _ = imap.append(папка, "\\Seen",
                             imaplib.Time2Internaldate(когда.timestamp()),
                             mime_bytes)
        if тип != "OK":
            logger.warning("копия в отправленные: APPEND вернул %s", тип)
            return False
        return True
    except Exception:  # noqa: BLE001 - письмо уже ушло, копия не смеет ронять
        logger.exception("копия в отправленные не легла (%s)",
                         getattr(mb_cfg, "mailbox_id", "?"))
        return False
    finally:
        if imap is not None:
            try:
                imap.logout()
            except Exception:  # noqa: BLE001
                pass
