# -*- coding: utf-8 -*-
"""Рубеж направления не должен гаснуть от одной опальной учётки.

25.08.2026: пять отказов Яндекса «подозрение на спам» у одного
a.kozlov@zernosort.ru поставили на паузу ШЕСТЬ чужих мейеровских ящиков,
у которых отказов не было ни одного. Сам козлов к тому мигу уже стоял по
своему порогу — вина зачлась дважды.

Правка: направление душим, только когда отказы пришли не с одного адреса
(порог gates.otkaz_min_yashchikov, по умолчанию 2; 1 — прежнее поведение).

Каталог C:\\sender\\sender делят несколько сессий, поэтому файлы целиком НЕ
заливаем: правим по якорям в серверном тексте, каждый якорь обязан
встретиться ровно один раз. Порядок жёсткий: .bak, запись, py_compile;
сбой на любом файле откатывает оба.

    pl_run.py rubezh_ne_gasit_sosedey.py            # вхолостую
    pl_run.py rubezh_ne_gasit_sosedey.py primenit   # применить
"""
import io
import os
import py_compile
import shutil
import sys
import time

КОРЕНЬ = r"C:\sender\sender"
ПРИМЕНИТЬ = "primenit" in sys.argv[1:]

ЯКОРЬ_ПОРОГ = """ПОРОГ_ЯЩИКА = 2
ПОРОГ_НАПРАВЛЕНИЯ = 5
"""
ЗАМЕНА_ПОРОГ = """ПОРОГ_ЯЩИКА = 2
ПОРОГ_НАПРАВЛЕНИЯ = 5
# Сколько РАЗНЫХ ящиков направления должны словить отказ, чтобы душить пул.
# Одна опальная учётка — её собственная беда, а не беда общих доменов.
МИН_ЯЩИКОВ = 2
"""

ЯКОРЬ_POROGI = '''def porogi(config) -> tuple[int, int]:
    """(порог по ящику, порог по направлению) из конфига; 0 — рубеж выключен."""
    def _взять(ключ: str, по_умолчанию: int) -> int:
        try:
            з = config.get(ключ, None)
        except Exception:                                          # noqa: BLE001
            return по_умолчанию
        if з is None or str(з).strip() == "":
            return по_умолчанию
        try:
            return max(0, int(з))
        except (TypeError, ValueError):
            return по_умолчанию

    return (_взять("gates.otkaz_stop_yashchik", ПОРОГ_ЯЩИКА),
            _взять("gates.otkaz_stop_napravlenie", ПОРОГ_НАПРАВЛЕНИЯ))'''
ЗАМЕНА_POROGI = '''def _iz_config(config, ключ: str, по_умолчанию: int) -> int:
    """Целое из конфига, не роняясь ни на отсутствии ключа, ни на мусоре."""
    try:
        з = config.get(ключ, None)
    except Exception:                                              # noqa: BLE001
        return по_умолчанию
    if з is None or str(з).strip() == "":
        return по_умолчанию
    try:
        return max(0, int(з))
    except (TypeError, ValueError):
        return по_умолчанию


def porogi(config) -> tuple[int, int]:
    """(порог по ящику, порог по направлению) из конфига; 0 — рубеж выключен."""
    return (_iz_config(config, "gates.otkaz_stop_yashchik", ПОРОГ_ЯЩИКА),
            _iz_config(config, "gates.otkaz_stop_napravlenie", ПОРОГ_НАПРАВЛЕНИЯ))


def min_yashchikov(config) -> int:
    """Сколько разных ящиков направления должны словить отказ для общей паузы.

    СЛУЧАЙ 25.08.2026. Пять отказов ОДНОГО a.kozlov@zernosort.ru погасили
    шесть чужих мейеровских ящиков, у которых отказов не было ни одного:
    счёт направления складывал всё подряд, и одной опальной учётки хватало,
    чтобы остановить направление на сутки. Свой ящик к тому мигу уже стоял
    по собственному порогу — то есть вина была зачтена дважды.

    Рубеж направления заведён про ОБЩИЕ ДОМЕНЫ («придушивают их вместе»), а
    общая беда видна тем, что отказы идут не с одного адреса. Порог 1 —
    прежнее поведение.
    """
    return _iz_config(config, "gates.otkaz_min_yashchikov", МИН_ЯЩИКОВ)'''

ЯКОРЬ_ИМПОРТ = """                               eto_otkaz_spam, nachalo_sutok,
                               porogi, prichina_pauzy)"""
ЗАМЕНА_ИМПОРТ = """                               eto_otkaz_spam, min_yashchikov,
                               nachalo_sutok, porogi, prichina_pauzy)"""

ЯКОРЬ_РУБЕЖ = '''        всего = sum(_счёт(mailbox_id=m) for m in соседи)
        if всего >= порог_напр:
            for m in соседи:
                self._pauza(m, prichina_pauzy(всего, f"направление {напр}"))'''
ЗАМЕНА_РУБЕЖ = '''        счета = {m: _счёт(mailbox_id=m) for m in соседи}
        всего = sum(счета.values())
        # Рубеж направления — про ОБЩИЕ ДОМЕНЫ, а не про одну опальную учётку.
        # 25.08.2026: пять отказов одного a.kozlov@zernosort.ru погасили шесть
        # чужих мейеровских ящиков, у которых отказов не было ни одного, — и
        # сам он к тому мигу уже стоял по своему порогу, то есть вина была
        # зачтена дважды. Беда общая тогда, когда отказы идут не с одного
        # адреса; порог gates.otkaz_min_yashchikov=1 возвращает прежнее.
        с_отказами = sum(1 for н in счета.values() if н)
        if всего >= порог_напр and с_отказами >= min_yashchikov(self.config):
            for m in соседи:
                self._pauza(m, prichina_pauzy(всего, f"направление {напр}"))'''

ПРАВКИ = [("otkaz_spam.py", [(ЯКОРЬ_ПОРОГ, ЗАМЕНА_ПОРОГ),
                             (ЯКОРЬ_POROGI, ЗАМЕНА_POROGI)]),
          ("sender.py", [(ЯКОРЬ_ИМПОРТ, ЗАМЕНА_ИМПОРТ),
                         (ЯКОРЬ_РУБЕЖ, ЗАМЕНА_РУБЕЖ)])]

готово = {}
for имя, пары in ПРАВКИ:
    п = os.path.join(КОРЕНЬ, имя)
    т = io.open(п, encoding="utf-8").read()
    for якорь, замена in пары:
        н = т.count(якорь)
        сдел = т.count(замена.strip().splitlines()[0])
        print("%s: якорь «%s…» найден %d раз"
              % (имя, якорь.strip().splitlines()[0][:52], н))
        if н == 0 and "min_yashchikov" in т:
            print("   правка уже стоит на сервере — пропускаю файл")
            break
        if н != 1:
            raise SystemExit("ОТМЕНА: якорь должен встречаться ровно один раз")
        т = т.replace(якорь, замена)
    else:
        готово[п] = т

if not готово:
    print("\nправить нечего")
    raise SystemExit(0)
if not ПРИМЕНИТЬ:
    print("\nвхолостую. Применить — аргумент primenit")
    raise SystemExit(0)

метка = time.strftime("%Y%m%d-%H%M%S")
записаны = []
try:
    for п, т in готово.items():
        shutil.copy2(п, п + ".bak-" + метка)
        io.open(п, "w", encoding="utf-8", newline="").write(т)
        py_compile.compile(п, doraise=True)
        записаны.append(п)
        print("правлено: %s (копия .bak-%s)" % (п, метка))
except Exception as e:  # noqa: BLE001
    print("СБОЙ: %s — откатываю всё" % e)
    for п in записаны:
        shutil.copy2(п + ".bak-" + метка, п)
    raise
print("\nготово. Панель подхватит после Restart-Service SenderPanel -Force")
