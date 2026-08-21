# -*- coding: utf-8 -*-
"""Маяки: свои адреса в чужих почтовиках, чтобы видеть ПАПКУ, а не догадки.

ЗАЧЕМ. По SMTP папку узнать нельзя: разговор кончается на «250 принял», а
куда письмо легло — во «Входящие» или в «Спам» — решается уже внутри
почтовика и отправителю не сообщается. Постмастер mail.ru показывает это
средним по домену и только для своих получателей; про конкретный текст он
молчит. Маяк отвечает ровно на этот вопрос: то же самое письмо уходит на
наш собственный ящик у mail.ru/Яндекса/Gmail, и через час мы смотрим по
IMAP, в какой он папке.

ТРИ ПРАВИЛА, БЕЗ КОТОРЫХ ЗАМЕР ВРЁТ ИЛИ ВРЕДИТ:

1. МАЯК НЕ НА НАШЕМ ДОМЕНЕ. Письмо с optic-sort.ru на optic-sort.ru не
   проходит внешний фильтр вообще. Маяк обязан жить там, где живёт база:
   mail.ru, Яндекс, Gmail, и хорошо бы один на корпоративном сервере.

2. МАЯК НЕ ЗАВОДИТ ЛИД И НЕ ПОПАДАЕТ В СТАТИСТИКУ. Панель читает наши
   ящики по IMAP, и ответ самому себе легко превращается в карточку лида, а
   отправка — в лишнюю единицу в знаменателе. Поэтому у маяков своя
   служебная кампания, она вычитается из счётчиков (store.count_events
   exclude_campaign_ids) и не попадает в ленту.

3. ПИСЬМО ДОЛЖНО БЫТЬ ТЕМ ЖЕ САМЫМ. Иначе мы измерим не свою рассылку, а
   специально сделанную открытку: заголовки, подпись, ссылки и отправитель
   влияют на папку не меньше текста.

КЛЮЧИ И ПАРОЛИ В КОНФИГЕ НЕ ХРАНИМ: у каждого маяка имя переменной
окружения, из которой берётся пароль.

Конфиг:
  mayaki:
    vklyucheny: true
    v_partiyu: 1              # сколько маяков подмешивать в одну партию
    zaderzhka_min: 60         # через сколько минут смотреть папку
    spisok:
      - email: proverka@mail.ru
        provayder: mail.ru
        imap_host: imap.mail.ru
        papka_spam: Спам
        parol_env: MAYAK_MAILRU_1
"""
from __future__ import annotations

import email.header
import imaplib
import os
from dataclasses import dataclass
from typing import Optional

КАМПАНИЯ = "маяки (служебная)"
СОБЫТИЕ = "mayak"

# Имена папки «Спам» у разных почтовиков. IMAP-имя может отличаться от
# показанного в вебе, поэтому пробуем несколько и ещё спрашиваем LIST.
ПАПКИ_СПАМА = ("Спам", "Spam", "Junk", "[Gmail]/Спам", "[Gmail]/Spam",
               "INBOX.Spam", "Junk E-mail")


@dataclass(frozen=True)
class Mayak:
    email: str
    provayder: str
    imap_host: str
    imap_port: int = 993
    login: str = ""
    parol_env: str = ""
    papka_spam: str = ""

    @property
    def polzovatel(self) -> str:
        return self.login or self.email

    def parol(self) -> Optional[str]:
        return os.environ.get(self.parol_env) if self.parol_env else None


def nastroyki(config) -> dict:
    """Настройки маяков с безопасными значениями по умолчанию."""
    def _взять(ключ, по_умолчанию):
        try:
            з = config.get(f"mayaki.{ключ}", None)
        except Exception:                                          # noqa: BLE001
            return по_умолчанию
        return по_умолчанию if з is None else з

    return {
        "включены": bool(_взять("vklyucheny", False)),
        "в_партию": max(0, int(_взять("v_partiyu", 1) or 0)),
        "задержка_мин": max(1, int(_взять("zaderzhka_min", 60) or 60)),
    }


def spisok(config) -> list[Mayak]:
    """Маяки из конфига. Без пароля в окружении маяк не берём: молча
    промолчавший IMAP хуже отсутствующего маяка."""
    try:
        сырое = config.get("mayaki.spisok", []) or []
    except Exception:                                              # noqa: BLE001
        return []
    вышло: list[Mayak] = []
    for э in сырое:
        if not isinstance(э, dict) or not э.get("email"):
            continue
        м = Mayak(
            email=str(э["email"]).strip().lower(),
            provayder=str(э.get("provayder") or "").strip().lower(),
            imap_host=str(э.get("imap_host") or "").strip(),
            imap_port=int(э.get("imap_port") or 993),
            login=str(э.get("login") or "").strip(),
            parol_env=str(э.get("parol_env") or "").strip(),
            papka_spam=str(э.get("papka_spam") or "").strip(),
        )
        вышло.append(м)
    return вышло


def eto_mayak(email_adres: str, config) -> bool:
    """Этот адрес — маяк? Спрашивают лента лидов и отбор получателей."""
    а = str(email_adres or "").strip().lower()
    return any(м.email == а for м in spisok(config))


def _dekod(значение) -> str:
    """Тема письма из IMAP приходит в MIME-кодировке — разворачиваем."""
    if isinstance(значение, bytes):
        значение = значение.decode("utf-8", "replace")
    куски = email.header.decode_header(str(значение or ""))
    вышло = []
    for текст, кодировка in куски:
        if isinstance(текст, bytes):
            вышло.append(текст.decode(кодировка or "utf-8", "replace"))
        else:
            вышло.append(текст)
    return "".join(вышло)


def papki(соединение) -> list[str]:
    """Список папок ящика — чтобы найти «Спам» по факту, а не по догадке."""
    ок, данные = соединение.list()
    if ок != "OK":
        return []
    имена = []
    for строка in данные or []:
        if isinstance(строка, bytes):
            строка = строка.decode("utf-8", "replace")
        часть = str(строка).split(' "/" ')[-1].strip().strip('"')
        if часть:
            имена.append(часть)
    return имена


def gde_pismo(m: Mayak, tema: str, *, timeout: int = 30) -> dict:
    """В какой папке лежит письмо с этой темой: входящие, спам или нет его.

    Ищем ПО ТЕМЕ, а не по Message-ID: почтовики переписывают идентификатор
    при пересылке, а тема остаётся. Возвращаем и папку, и то, что именно
    просмотрели, — чтобы «не найдено» можно было отличить от «не искали».
    """
    пароль = m.parol()
    if not пароль:
        return {"папка": "нет пароля", "искали": [],
                "почему": f"переменная {m.parol_env} пуста"}
    искали: list[str] = []
    try:
        с = imaplib.IMAP4_SSL(m.imap_host, m.imap_port, timeout=timeout)
    except Exception as ex:                                        # noqa: BLE001
        return {"папка": "нет связи", "искали": [],
                "почему": f"{type(ex).__name__}: {str(ex)[:80]}"}
    try:
        с.login(m.polzovatel, пароль)
        все_папки = papki(с)
        кандидаты = [p for p in ([m.papka_spam] if m.papka_spam else [])
                     + list(ПАПКИ_СПАМА) if p]
        спам = [p for p in кандидаты if p in все_папки] or \
               [p for p in все_папки if "spam" in p.lower() or "спам" in p.lower()]
        порядок = ["INBOX"] + спам[:2]
        for папка in порядок:
            try:
                ок, _ = с.select(f'"{папка}"', readonly=True)
                if ок != "OK":
                    continue
                искали.append(папка)
                ок, данные = с.search(None, "ALL")
                if ок != "OK":
                    continue
                ids = (данные[0].split() if данные and данные[0] else [])[-40:]
                for i in reversed(ids):
                    ок, стр = с.fetch(i, "(BODY[HEADER.FIELDS (SUBJECT)])")
                    if ок != "OK" or not стр or not стр[0]:
                        continue
                    сырое = стр[0][1] if isinstance(стр[0], tuple) else стр[0]
                    т = _dekod(сырое).replace("Subject:", "").strip()
                    if tema and tema[:60].strip().lower() in т.lower():
                        return {"папка": ("входящие" if папка.upper() == "INBOX"
                                          else "спам"),
                                "искали": искали, "почему": "",
                                "папка_имя": папка}
            except Exception as ex:                                # noqa: BLE001
                искали.append(f"{папка} (ошибка {type(ex).__name__})")
        return {"папка": "не найдено", "искали": искали,
                "почему": "письма с такой темой в просмотренных папках нет"}
    finally:
        try:
            с.logout()
        except Exception:                                          # noqa: BLE001
            pass
