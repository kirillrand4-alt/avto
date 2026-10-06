# -*- coding: utf-8 -*-
"""Новый ответ клиента поднимает закрытую карточку обратно в ленту.

Карточку закрывают по тому, что клиент написал ТОГДА, и это нормально.
Но потом он пишет снова — и ответ ложился в закрытую карточку молча:
статус оставался «не интересно», в ленту она не возвращалась, продавец её
не видел. 16.09 так пропало «может они окажутся лучше и мы у Вас купим»
от «Сташевского» на карточке, закрытой 10.09 по первому ответу «у нас
стоит 2 фотосепаратора».

argv: --primenit чтобы записать.
"""
import io
import py_compile
import sys
import time

ФАЙЛ = r"C:\sender\sender\leaddesk.py"
ПРИМЕНИТЬ = "--primenit" in sys.argv

ЯКОРЬ1 = '''        # проброс в Bitrix (если настроен) только для НОВЫХ лидов
        if created and self._bitrix is not None:'''
ЗАМЕНА1 = '''        # НОВЫЙ ОТВЕТ ПОДНИМАЕТ ОТЛОЖЕННУЮ КАРТОЧКУ. Закрыли её по тому,
        # что клиент написал ТОГДА, и это нормально. Но он пишет снова — а
        # ответ ложился в закрытую карточку молча: статус оставался «не
        # интересно», в ленту она не возвращалась, продавец её не видел.
        # 16.09 так пропало «может они окажутся лучше и мы у Вас купим» от
        # «Сташевского» на карточке, закрытой 10.09 по первому ответу «у
        # нас стоит 2 фотосепаратора».
        if not created:
            self._podnyat_otlozhennuyu(lead_id, reply_kind)
        # проброс в Bitrix (если настроен) только для НОВЫХ лидов
        if created and self._bitrix is not None:'''

ЯКОРЬ2 = '''    @staticmethod
    def _parse_snippet(snippet: str) -> tuple[Optional[str], Optional[str], str]:'''
ЗАМЕНА2 = '''    # Статусы, из которых новый ответ возвращает карточку в ленту: это то,
    # что отложили МЫ САМИ. «Передали в Битрикс» и «закрыт» не трогаем —
    # там карточка живёт своей жизнью, и подъём сбил бы работу продавца.
    _ОТЛОЖЕННЫЕ = ("not_interested", "avtootvet", "v_otpuske")
    # Ответы, которые поднимать нечему: автоответ о намерении не говорит
    # ничего, отказ и просьба не писать говорят обратное.
    _НЕ_ПОДНИМАЮТ = ("auto_reply", "not_interested", "unsub_request")

    def _podnyat_otlozhennuyu(self, lead_id: int, reply_kind) -> None:
        """Вернуть отложенную карточку в ленту по живому ответу человека."""
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
уже = "_podnyat_otlozhennuyu" in т
print("файл: %s (%d байт), правка уже стоит: %s"
      % (ФАЙЛ, len(т), "да" if уже else "нет"))
if уже:
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
print("   стало байт: %d (+%d)" % (len(новый), len(новый) - len(т)))
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
