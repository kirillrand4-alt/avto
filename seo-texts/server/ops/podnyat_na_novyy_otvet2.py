# -*- coding: utf-8 -*-
"""Новый ответ поднимает отложенную карточку. Правка по ЖИВОМУ файлу.

Первая попытка не легла: на сервере leaddesk.py новее репозитория —
push_warm_lead принимает status и v_bitrix и сам решает, с каким статусом
заводить карточку. Поэтому якорь берём из живого файла, а решение о
подъёме сверяем ещё и с этим статусом: если вызывающий сам пометил
карточку автоответом или отпуском, поднимать нечего.

argv: --primenit чтобы записать.
"""
import io
import py_compile
import sys
import time

ФАЙЛ = r"C:\sender\sender\leaddesk.py"
ПРИМЕНИТЬ = "--primenit" in sys.argv

ЯКОРЬ1 = '''        # проброс в Bitrix (если настроен) только для НОВЫХ лидов
        # Bitrix — только по решению оператора (он переводит лид в очередь'''
ЗАМЕНА1 = '''        # НОВЫЙ ОТВЕТ ПОДНИМАЕТ ОТЛОЖЕННУЮ КАРТОЧКУ. Закрыли её по тому,
        # что клиент написал ТОГДА, и это нормально. Но он пишет снова — а
        # ответ ложился в закрытую карточку молча: статус оставался «не
        # интересно», в ленту она не возвращалась, продавец её не видел.
        # 16.09 так пропало «может они окажутся лучше и мы у Вас купим» от
        # «Сташевского» на карточке, закрытой 10.09 по первому ответу «у
        # нас стоит 2 фотосепаратора».
        if not created:
            self._podnyat_otlozhennuyu(lead_id, reply_kind, статус)
        # проброс в Bitrix (если настроен) только для НОВЫХ лидов
        # Bitrix — только по решению оператора (он переводит лид в очередь'''

ЯКОРЬ2 = '''    @staticmethod
    def _parse_snippet(snippet: str) -> tuple[Optional[str], Optional[str], str]:'''
ЗАМЕНА2 = '''    # Статусы, из которых новый ответ возвращает карточку в ленту: это то,
    # что отложили МЫ САМИ. «Передали в Битрикс» и «закрыт» не трогаем —
    # там карточка живёт своей жизнью, и подъём сбил бы работу продавца.
    _ОТЛОЖЕННЫЕ = ("not_interested", "avtootvet", "v_otpuske")
    # Ответы, которые поднимать нечему: автоответ о намерении не говорит
    # ничего, отказ и просьба не писать говорят обратное.
    _НЕ_ПОДНИМАЮТ = ("auto_reply", "not_interested", "unsub_request")

    def _podnyat_otlozhennuyu(self, lead_id: int, reply_kind,
                              статус_вызова: str = "new") -> None:
        """Вернуть отложенную карточку в ленту по живому ответу человека.

        статус_вызова — с каким статусом вызывающий просил завести карточку.
        Не «new» означает, что он сам считает письмо автоответом или
        отпуском: поднимать нечего.
        """
        if str(статус_вызова or "new") != "new":
            return
        if str(reply_kind or "") in self._НЕ_ПОДНИМАЮТ:
            return
        try:
            lead = self._store.get_lead(lead_id)
            if lead is None:
                return
            if str(getattr(lead, "status", "") or "") not in self._ОТЛОЖЕННЫЕ:
                return
            self._store.update_lead_cas(
                lead_id, expected_version=lead.version,
                action="поднят новым ответом", status="new")
        except Exception:  # noqa: BLE001 - подъём не должен ронять приём почты
            logger.exception("карточка %s не поднялась по новому ответу", lead_id)

    @staticmethod
    def _parse_snippet(snippet: str) -> tuple[Optional[str], Optional[str], str]:'''

т = io.open(ФАЙЛ, encoding="utf-8").read()
if "_podnyat_otlozhennuyu" in т:
    raise SystemExit("правка уже применена")
беда = []
for имя, як in (("вызов", ЯКОРЬ1), ("метод", ЯКОРЬ2)):
    n = т.count(як)
    print("   якорь «%s»: вхождений %d" % (имя, n))
    if n != 1:
        беда.append(имя)
if беда:
    raise SystemExit("НЕ ТРОГАЕМ: якоря не сошлись (%s)" % ", ".join(беда))
новый = т.replace(ЯКОРЬ1, ЗАМЕНА1, 1).replace(ЯКОРЬ2, ЗАМЕНА2, 1)
print("   файл: %d → %d байт (+%d)" % (len(т), len(новый), len(новый) - len(т)))
if not ПРИМЕНИТЬ:
    print("")
    print("=" * 74)
    print("=== ПОКАЗ БЕЗ ЗАПИСИ (нужен --primenit) ===")
    raise SystemExit(0)

бэкап = ФАЙЛ + ".bak-%d" % int(time.time())
io.open(бэкап, "w", encoding="utf-8").write(т)
io.open(ФАЙЛ, "w", encoding="utf-8").write(новый)
try:
    py_compile.compile(ФАЙЛ, doraise=True)
    итог = "записано, компилируется"
except Exception as ex:                                         # noqa: BLE001
    io.open(ФАЙЛ, "w", encoding="utf-8").write(т)
    итог = "НЕ КОМПИЛИРУЕТСЯ, откатили: %s" % str(ex)[:160]
print("")
print("=" * 74)
print("=== ПОДЪЁМ КАРТОЧКИ ПО НОВОМУ ОТВЕТУ ===")
print("   бэкап: %s" % бэкап)
print("   итог:  %s" % итог)
