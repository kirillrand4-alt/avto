# -*- coding: utf-8 -*-
"""Выкатить общий разборщик направления письма на боевой sender/.

ЗАЧЕМ. 20.08 копии второму контакту «Гастрофабрики» ушли с компрессорных
ящиков под мейеровским письмом (рентген-инспекция, оптическая сортировка) и
за подписью «Компрессор Центр». Гейт направлений на авто-пути читал только
panel.letter_division и метку компании; у карточек копий поля нет, метка
составная - гейт молчал. Ручной экран те же письма спас бы: он смотрит ещё
и товарную лексику письма. Теперь разборщик ОДИН на оба пути.

ЗАЛИВАЕМ ХИРУРГИЧЕСКИ, А НЕ ЦЕЛИКОМ. Каталог C:\\sender\\sender делят
несколько сессий, и sha серверных файлов не совпадает с нашей веткой.
Поэтому: новый модуль кладём файлом, а в sender.py и confirm.py меняем
ровно два куска по якорям, сверяя, что якорь найден РОВНО ОДИН раз.
Перед записью - .bak с меткой времени, после записи - компиляция.

Сухой прогон по умолчанию. Катить: --katit
"""
import io
import json
import os
import py_compile
import sys
import time

ПОСЫЛКА = '{"modul": "# -*- coding: utf-8 -*-\\n\\"\\"\\"Про какое направление ПИСЬМО — один разборщик на оба пути отправки.\\n\\nЗАЧЕМ ОТДЕЛЬНЫЙ МОДУЛЬ. Направление письма спрашивают два слоя, и до\\n21.08 каждый спрашивал по-своему:\\n\\n  * ручной экран (confirm.ConfirmSend.letter_division) — сначала поле\\n    panel.letter_division от генератора, а если его нет, ТОВАРНАЯ ЛЕКСИКА\\n    самого письма;\\n  * авто-отправка (sender.Sender._napravlenie_pisma) — только поле, плюс\\n    метка компании из карточки; лексику письма не смотрел вовсе.\\n\\nИз-за этой разницы ящик подбирался по-разному. 20.08 копии второму\\nконтакту «Гастрофабрики» ушли с компрессорных адресов\\n(m.pavlov@kompressor-pro-trade.ru, v.melnikov@kompressor-air-trade.ru) под\\nмейеровским письмом про рентген-инспекцию и оптическую сортировку: у\\nкарточек копий поля letter_division не оказалось, ручной путь спас бы их\\nлексикой, а авто-путь промолчал — и подпись ушла «Компрессор Центр».\\nВладелец: «когда вручную делал копии и отправлял, отправил не проверив\\nнаправление».\\n\\nПравило одно: поле генератора → лексика письма → не знаем (None). «Не\\nзнаем» не значит «можно любой ящик»: у вызывающего есть свои запасные\\nисточники (метка компании), и они остаются на своей стороне.\\n\\"\\"\\"\\nfrom __future__ import annotations\\n\\nfrom typing import Optional\\n\\n# Товарная лексика направлений — зеркало ai_letter._EQUIP_MARKERS. Держим\\n# копию, чтобы ни confirm, ни sender не тянули генератор ради двух кортежей.\\nМАРКЕРЫ = {\\n    \\"kc\\": (\\"компрессор\\", \\"азот\\", \\"кислород\\", \\" мкс\\", \\"пневмо\\", \\"воздуходув\\"),\\n    \\"meyer\\": (\\"рентген\\", \\"фотосепар\\", \\"фото-сепар\\", \\"инспекц\\", \\"сортировк\\"),\\n}\\n\\n\\ndef po_leksike(текст: str) -> Optional[str]:\\n    \\"\\"\\"kc|meyer|None по товарной лексике. Обе сразу — не гадаем.\\"\\"\\"\\n    т = str(текст or \\"\\").lower()\\n    if not т.strip():\\n        return None\\n    попало = {k for k, ms in МАРКЕРЫ.items() if any(m in т for m in ms)}\\n    return next(iter(попало)) if len(попало) == 1 else None\\n\\n\\ndef napravlenie_pisma(row: dict) -> Optional[str]:\\n    \\"\\"\\"kc|meyer|None — про КАКОЕ направление письмо в этой карточке.\\n\\n    Компания бывает «kc+meyer», но письмо всегда про ОДНО направление\\n    (ai_letter.target_division). Ящик обязан совпадать с письмом: подпись и\\n    домен строятся по направлению ЯЩИКА, и мейеровское письмо с\\n    компрессорного адреса получатель читает как чужую подпись.\\n\\n    Источники по убыванию надёжности:\\n      1) panel.letter_division — направление, выбранное генератором;\\n      2) лексика самого письма — для карточек, которым поле не проставили:\\n         письма старше поля, часть новостных и КОПИИ вторым контактам.\\n    \\"\\"\\"\\n    if not isinstance(row, dict):\\n        return None\\n    panel = row.get(\\"panel\\") if isinstance(row.get(\\"panel\\"), dict) else {}\\n    d = str((panel or {}).get(\\"letter_division\\") or \\"\\").strip().lower()\\n    if d in МАРКЕРЫ:\\n        return d\\n    letter = (panel or {}).get(\\"letter\\")\\n    if not isinstance(letter, dict):\\n        letter = {}\\n    return po_leksike(\\" \\".join([\\n        str(row.get(\\"subject\\") or \\"\\"), str(row.get(\\"body\\") or \\"\\"),\\n        str(row.get(\\"edited_subject\\") or \\"\\"), str(row.get(\\"edited_body\\") or \\"\\"),\\n        str(letter.get(\\"subject\\") or \\"\\"), str(letter.get(\\"body\\") or \\"\\"),\\n    ]))\\n", "sender_block": "    def _napravlenie_pisma(self, message) -> Optional[str]:\\n        \\"\\"\\"kc|meyer|None — про КАКОЕ направление письмо, привязанное к message.\\n\\n        Разбор ОБЩИЙ с ручным экраном (sender.napravlenie_pisma): поле\\n        panel.letter_division от генератора, а если его нет — товарная\\n        лексика самого письма.\\n\\n        ЛЕКСИКА ЗДЕСЬ ПОЯВИЛАСЬ 21.08, И ВОТ ПОЧЕМУ. Раньше авто-путь читал\\n        только поле и метку компании, а ручной экран — ещё и лексику. Копии\\n        второму контакту карточку получают, а поля letter_division у них\\n        нет: 20.08 два письма «Гастрофабрике» про рентген-инспекцию и\\n        оптическую сортировку ушли с компрессорных ящиков\\n        (m.pavlov@kompressor-pro-trade.ru, v.melnikov@kompressor-air-trade.ru)\\n        за подписью «Компрессор Центр». Метка компании их не спасла:\\n        «kc+meyer» составное и направления не решает.\\n\\n        Метка компании остаётся ПОСЛЕ лексики: текст письма — прямая улика,\\n        метка — косвенная.\\n        \\"\\"\\"\\n        mid = getattr(message, \\"id\\", None)\\n        if mid is None:\\n            return None\\n        try:\\n            row = self.store.confirm_review_for_message(int(mid))\\n        except Exception:  # noqa: BLE001 - нет метода/строки: гейт не строже\\n            return None\\n        if not row:\\n            return None\\n        d = napravlenie_pisma(row)\\n        if d:\\n            return d\\n        # ПОЛЕ ПУСТОЕ И ЛЕКСИКА МОЛЧИТ — НЕ ПОВОД ПРОПУСКАТЬ ЛЮБОЙ ЯЩИК\\n        # (владелец 17.08: «при автоотправке ящик не мог чужого направления\\n        # подтянуться, отправленные несколько мейер так были»).\\n        #\\n        # Запасной источник берём из ТОЙ ЖЕ панели: карточка компании несёт\\n        # своё направление (infopanel._company_block). Лишних чтений нет.\\n        # Составное «kc+meyer» не решает: там оба ящика законны, и гейт\\n        # остаётся на прежнем правиле «подходит ли компании направление\\n        # ящика».\\n        panel = row.get(\\"panel\\") if isinstance(row.get(\\"panel\\"), dict) else {}\\n        c = (panel or {}).get(\\"company\\")\\n        if isinstance(c, dict):\\n            d2 = str(c.get(\\"division\\") or \\"\\").strip().lower()\\n            if d2 in (\\"kc\\", \\"meyer\\"):\\n                return d2\\n        return None\\n\\n", "confirm_block": "    # Товарная лексика направлений живёт в sender.napravlenie_pisma —\\n    # ОДНОМ разборщике на ручной путь и на авто-отправку (21.08: копии\\n    # «Гастрофабрике» ушли с компрессорных ящиков потому, что авто-путь\\n    # лексику не смотрел). Имя оставлено прежним: на него смотрят тесты.\\n    _LETTER_DIV_MARKERS = МАРКЕРЫ_НАПРАВЛЕНИЙ\\n\\n    def letter_division(self, row: dict) -> Optional[str]:\\n        \\"\\"\\"kc|meyer|None — про КАКОЕ направление письмо в этой карточке.\\n\\n        Разбор общий с авто-отправкой (sender.napravlenie_pisma): поле\\n        panel.letter_division от генератора, а если его нет — товарная\\n        лексика письма. Ящик обязан совпадать с письмом, иначе письмо про\\n        фотосепараторы уходит с компрессорного адреса и с подписью\\n        менеджера КЦ — направление у ящика своё, и гейт по компании его не\\n        ловит, потому что компании разрешены оба.\\n        \\"\\"\\"\\n        return napravlenie_pisma(row)\\n\\n", "sender_import": ["from sender.gates import young_domain_reason  # noqa: E402", "from sender.napravlenie_pisma import napravlenie_pisma  # noqa: E402"], "confirm_import": ["from sender.errors import SenderError, ValidationError", "from sender.napravlenie_pisma import (МАРКЕРЫ as МАРКЕРЫ_НАПРАВЛЕНИЙ,\\n                                      napravlenie_pisma)"]}'

КОРЕНЬ = r"C:\sender\sender"
КАТИТЬ = "--katit" in sys.argv
ДАННЫЕ = json.loads(ПОСЫЛКА)


def _прочесть(имя):
    return io.open(os.path.join(КОРЕНЬ, имя), encoding="utf-8").read()


def _записать(имя, текст):
    путь = os.path.join(КОРЕНЬ, имя)
    if os.path.exists(путь):
        копия = f"{путь}.bak-{int(time.time())}"
        io.open(копия, "w", encoding="utf-8", newline="").write(_прочесть(имя))
        print(f"  .bak: {os.path.basename(копия)}")
    with io.open(путь, "w", encoding="utf-8", newline="") as f:
        f.write(текст)
        f.flush()
        os.fsync(f.fileno())
    py_compile.compile(путь, doraise=True)
    print(f"  записан и скомпилирован: {имя} ({len(текст)} знаков)")


def _замена_блока(текст, начало, конец, новый, имя):
    """Заменить кусок между двумя якорями. Оба обязаны быть уникальны."""
    for як in (начало, конец):
        if текст.count(як) != 1:
            raise SystemExit(f"{имя}: якорь встречается {текст.count(як)} раз, "
                             f"а должен один: {як[:60]!r}")
    i, j = текст.index(начало), текст.index(конец)
    if i >= j:
        raise SystemExit(f"{имя}: якоря в неверном порядке")
    return текст[:i] + новый + текст[j:]


def _добавить_импорт(текст, якорь, строка, имя):
    if строка.split("\n")[0] in текст:
        print(f"  {имя}: импорт уже стоит")
        return текст
    if текст.count(якорь) != 1:
        raise SystemExit(f"{имя}: якорь импорта не уникален")
    return текст.replace(якорь, якорь + "\n" + строка, 1)


print("napravlenie_pisma.py:")
есть = os.path.exists(os.path.join(КОРЕНЬ, "napravlenie_pisma.py"))
print(f"  на сервере {'уже есть' if есть else 'нет'}; "
      f"наш размер {len(ДАННЫЕ['modul'])} знаков")

s = _прочесть("sender.py")
s2 = _добавить_импорт(s, ДАННЫЕ["sender_import"][0],
                      ДАННЫЕ["sender_import"][1], "sender.py")
s2 = _замена_блока(
    s2, "    def _napravlenie_pisma(self, message) -> Optional[str]:",
    "    def division_block(self, recipient, mailbox_id: str,",
    ДАННЫЕ["sender_block"], "sender.py")
print(f"sender.py: было {len(s)} знаков, станет {len(s2)}")
print(f"  лексика в гейте: {'napravlenie_pisma(row)' in s2}")

c = _прочесть("confirm.py")
c2 = _добавить_импорт(c, ДАННЫЕ["confirm_import"][0],
                      ДАННЫЕ["confirm_import"][1], "confirm.py")
c2 = _замена_блока(
    c2, "    # Товарная лексика направлений",
    "    def _next_in_rotation(self, candidates: list) -> Optional[str]:",
    ДАННЫЕ["confirm_block"], "confirm.py")
print(f"confirm.py: было {len(c)} знаков, станет {len(c2)}")

if not КАТИТЬ:
    print("\nсухой прогон, ничего не записано. Катить - --katit")
    raise SystemExit(0)

print("\nпишем:")
_записать("napravlenie_pisma.py", ДАННЫЕ["modul"])
_записать("sender.py", s2)
_записать("confirm.py", c2)

sys.path.insert(0, r"C:\sender")
for м in ("sender.napravlenie_pisma", "sender.confirm", "sender.sender"):
    sys.modules.pop(м, None)
from sender.napravlenie_pisma import napravlenie_pisma            # noqa: E402
проба = {"panel": {"company": {"division": "kc+meyer"}},
         "subject": "Для производства: контроль включений в готовой продукции",
         "body": "представляю компанию «Руспром Meyer». рентген-инспекция"}
print(f"\nпроба на карточке копии: {napravlenie_pisma(проба)} (ждём meyer)")
print("ПАНЕЛЬ НАДО ПЕРЕЗАПУСТИТЬ: Restart-Service SenderPanel -Force")
