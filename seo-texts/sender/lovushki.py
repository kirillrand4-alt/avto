# -*- coding: utf-8 -*-
"""Заслон от спам-ловушек: три повадки вместо несуществующих списков.

Публичных списков ловушек нет и не будет: смысл ловушки в том, что она
неотличима от обычного адреса. Спамхаус, Спамкоп и почтовые провайдеры
свои адреса не раскрывают — иначе рассыльщики вычистили бы их первыми.
Значит, ловим не по списку, а по повадкам:

  1. СЛУЖЕБНЫЙ АДРЕС — abuse@, postmaster@, spam@, security@. Такие ящики
     заводят для жалоб и наблюдения; коммерческое письмо туда — жалоба на
     нас же, причём написанная нашими руками;
  2. ВОСКРЕСШИЙ — адрес когда-то отбился как несуществующий, а сегодня
     принимает почту. Так устроена ПЕРЕРАБОТАННАЯ ловушка: провайдер держит
     брошенный ящик закрытым год, потом включает обратно — писать туда
     некому, значит пишет тот, кто взял адрес из старой базы;
  3. ОПЕЧАТКА В ДОМЕНЕ — mai.ru, yandx.ru, gmial.com. Их регистрируют под
     ловлю тех, кто не проверяет источник, и почти любая почта туда —
     чужая, попавшая по ошибке.

Про третье правило отдельно. Первая редакция сравнивала домены «по позициям»
и объявила ловушками maco.ru (реальный домен MACO, оконная фурнитура) и
diat.ru — ни один на популярный не похож даже на слух. Поэтому здесь считается
расстояние Дамерау–Левенштейна и берётся ТОЛЬКО дистанция 1: одна вставка,
удаление, замена или перестановка соседних букв. На дистанции 2 живут
настоящие домены, а живой контакт дороже гипотетической ловушки.

Правила 1 и 2 снимают письмо и заносят адрес в стоп-лист навсегда: служебный
ящик и воскресший мертвец коммерческого письма не ждут ни сегодня, ни через
месяц.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

СЛУЖЕБНЫЙ = "служебный"
ВОСКРЕСШИЙ = "воскресший"
ОПЕЧАТКА = "опечатка"

# Локальные части, за которыми не сидит покупатель компрессоров.
СЛУЖЕБНЫЕ = (
    "abuse", "postmaster", "hostmaster", "webmaster", "spam", "spamcop",
    "spamtrap", "trap", "security", "noc", "complaint", "complaints",
    "blacklist", "blocklist", "noreply", "no-reply", "donotreply",
    "do-not-reply", "devnull", "dev-null", "bounce", "bounces", "mailer-daemon",
    "root", "uucp", "listserv", "majordomo",
)

# Эталоны для правила опечаток. Короткие (ya.ru, bk.ru) в сравнении не
# участвуют: там одна буква — это четверть имени, ложных срабатываний
# будет больше, чем находок.
ПОПУЛЯРНЫЕ = (
    "mail.ru", "yandex.ru", "gmail.com", "bk.ru", "inbox.ru", "list.ru",
    "rambler.ru", "mail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "icloud.com", "internet.ru", "ya.ru", "yandex.com", "bk.com",
)
_МИН_ДЛИНА = 6


def _расстояние(a: str, b: str) -> int:
    """Дамерау–Левенштейн: вставка, удаление, замена, перестановка соседей."""
    п = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        п[i][0] = i
    for j in range(len(b) + 1):
        п[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            цена = 0 if a[i - 1] == b[j - 1] else 1
            п[i][j] = min(п[i - 1][j] + 1, п[i][j - 1] + 1,
                          п[i - 1][j - 1] + цена)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                п[i][j] = min(п[i][j], п[i - 2][j - 2] + 1)
    return п[len(a)][len(b)]


def похоже_на_опечатку(домен: str) -> Optional[str]:
    """Эталон, от которого домен отличается ровно на один шаг правки."""
    д = (домен or "").strip().lower()
    if len(д) < _МИН_ДЛИНА or д in ПОПУЛЯРНЫЕ:
        return None                       # сам эталон опечаткой себя не является
    for п in ПОПУЛЯРНЫЕ:
        if len(п) < _МИН_ДЛИНА or abs(len(д) - len(п)) > 1:
            continue
        if _расстояние(д, п) <= 1:
            return п
    return None


def служебный(адрес: str) -> Optional[str]:
    """Локальная часть — служебный ящик (abuse@, postmaster@, spam-report@)."""
    имя = (адрес or "").strip().lower().split("@", 1)[0]
    for с in СЛУЖЕБНЫЕ:
        if имя == с or имя.startswith(с + ".") or имя.startswith(с + "-") \
                or имя.startswith(с + "_"):
            return с
    return None


def вид_ловушки(адрес: str, *, отбивался: bool = False,
                живой_по_пробе: bool = False) -> Optional[tuple]:
    """(вид, объяснение) или None. Порядок — от самого надёжного правила."""
    а = (адрес or "").strip().lower()
    if "@" not in а:
        return None
    с = служебный(а)
    if с:
        return (СЛУЖЕБНЫЙ, f"служебный ящик {с}@ — не для коммерческих писем")
    if отбивался and живой_по_пробе:
        return (ВОСКРЕСШИЙ, "отбивался как несуществующий, теперь принимает "
                            "почту — повадка переработанной ловушки")
    п = похоже_на_опечатку(а.rsplit("@", 1)[-1])
    if п:
        return (ОПЕЧАТКА, f"домен на один знак от {п} — типовой домен-ловушка")
    return None


class ЗаслонЛовушек:
    """Проход по очереди: находит ловушки, при желании снимает письма.

    История отбивок берётся из стоп-листа (reason='bounce_hard'), «живой
    сегодня» — из кэша пробы. Обе выборки читаются один раз на проход:
    очередь в сотни писем, ходить в базу на каждое незачем.
    """

    def __init__(self, *, store: Any, probe: Any = None):
        self.store = store
        self.probe = probe

    # -- источники истории --------------------------------------------------- #

    def _отбивались(self) -> set:
        try:
            return self.store.suppression_values(reason="bounce_hard",
                                                 scope="email")
        except Exception:  # noqa: BLE001 - нет истории, правило просто молчит
            logger.exception("ловушки: не прочитался стоп-лист")
            return set()

    def _живые(self) -> set:
        if self.probe is None:
            return set()
        try:
            from sender.addr_probe import ЕСТЬ
            return self.probe.verdict_emails(ЕСТЬ)
        except Exception:  # noqa: BLE001
            logger.exception("ловушки: не прочитался кэш пробы")
            return set()

    # -- проход -------------------------------------------------------------- #

    def найти(self, письма: Iterable[dict]) -> list:
        отбивались, живые = self._отбивались(), self._живые()
        находки = []
        for r in письма:
            адрес = str(r.get("email") or "").strip().lower()
            if not адрес or (r.get("kind") or "outbound") == "reply":
                continue
            это = вид_ловушки(адрес, отбивался=адрес in отбивались,
                              живой_по_пробе=адрес in живые)
            if это:
                находки.append({"id": r.get("id"), "email": адрес,
                                "вид": это[0], "почему": это[1]})
        return находки

    def применить(self, письма: Iterable[dict]) -> dict:
        """Снять найденные письма с очереди и закрыть адреса навсегда."""
        находки = self.найти(письма)
        итог = {"найдено": len(находки), "снято": 0, "ид": set(),
                СЛУЖЕБНЫЙ: 0, ВОСКРЕСШИЙ: 0, ОПЕЧАТКА: 0}
        for н in находки:
            итог[н["вид"]] = итог.get(н["вид"], 0) + 1
            try:
                if self.store.confirm_decide(
                        int(н["id"]), status="skipped",
                        decided_by="заслон ловушек",
                        reason=f"{н['вид']}: {н['почему']}"):
                    итог["снято"] += 1
                    итог["ид"].add(н["id"])
                from sender.dtos import SuppressionIn
                self.store.suppression_add(SuppressionIn(
                    scope="email", value=н["email"], reason="spam_trap",
                    source="lovushki"))
            except Exception:  # noqa: BLE001 - одна находка не рвёт проход
                logger.exception("ловушки: не снялось письмо %s", н.get("id"))
        return итог
