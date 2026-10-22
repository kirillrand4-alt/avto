# -*- coding: utf-8 -*-
"""Автоотправка: свой лимит на проход у каждого направления (владелец 22.10:
«почему они вообще толкаются в очереди? у них же разные почты/домены» →
«давай что предложил»).

Было: проход брал наступившие одобренные письма по scheduled_at и слал, пока
не наберёт ОБЩИЙ batch. КЦ стоит в очереди раньше и съедал партию целиком,
Meyer со своими свободными ящиками ждал пауз КЦ (22.10: за час 2 письма Meyer
при 112 одобренных в очереди).

Стало: у КЦ, Meyer и «прочего» по своему batch на проход. Набрал направление
партию — его письма в этом проходе возвращаются в очередь, а кампании
направления больше не выбираются (store.claim_approved_due получил
skip_campaigns); другое направление идёт дальше. Лимиты ящиков, пейсинг,
окно получателя и все заслоны — без изменений.

Правка двух файлов по якорям: бэкап .bak-napr-<время>, py_compile обоих,
откат обоих при любом сбое. --otkat — вернуть оба из последних бэкапов.
После применения нужен Restart-Service SenderPanel -Force.
    napravleniya_auto_send.py [--primenit | --otkat] [--koren=<папка>]"""
import glob
import io
import os
import py_compile
import shutil
import sys
import time

КОРЕНЬ = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--koren=")), r"C:\sender\sender")
STORE = os.path.join(КОРЕНЬ, "store.py")
AUTO = os.path.join(КОРЕНЬ, "auto_send.py")
МЕТКА = "НАПРАВЛЕНИЯ-22.10"

ПРАВКИ = {
    STORE: [
        ("""    def claim_approved_due(self, *, now: datetime, limit: int,
                           skip_ids=None) -> list[Message]:""",
         """    def claim_approved_due(self, *, now: datetime, limit: int,
                           skip_ids=None, skip_campaigns=None) -> list[Message]:"""),
        ("""            параметры.extend(пропуск)
        параметры.append(int(limit))""",
         """            параметры.extend(пропуск)
        # skip_campaigns — кампании направления, чья партия в этом проходе
        # уже набрана (НАПРАВЛЕНИЯ-22.10): берём только письма других.
        камп = [int(x) for x in (skip_campaigns or [])][:500]
        if камп:
            условие += f" AND m.campaign_id NOT IN ({','.join('?' * len(камп))})"
            параметры.extend(камп)
        параметры.append(int(limit))"""),
    ],
    AUTO: [
        ("""        разобранные: set = set()
        # Потолок на проход: письмо, которому некуда идти, стоит нам одного
        # запроса, а не отправки. 40 партий по batch — с запасом на сегодняшнюю
        # очередь и без риска крутиться вечно.
        for _ in range(40):
            try:
                claimed = self.store.claim_approved_due(
                    now=now, limit=self.batch, skip_ids=разобранные)
            except TypeError:""",
         """        разобранные: set = set()
        # СВОЯ ПАРТИЯ У КАЖДОГО НАПРАВЛЕНИЯ (НАПРАВЛЕНИЯ-22.10, владелец:
        # «почему они вообще толкаются в очереди? у них же разные почты»).
        # Общая партия по scheduled_at доставалась тому, кто раньше в очереди:
        # 22.10 КЦ съедал её целиком, и Meyer со свободными ящиками за час
        # отправил 2 письма из 112 одобренных. Теперь у КЦ, Meyer и «прочего»
        # по batch на проход; набравшее партию направление выходит из выборки.
        напр_камп = self._napravleniya_kampaniy()
        по_напр: dict = {}
        набрано: set = set()
        всего_напр = max(1, len(set(напр_камп.values()) | {"прочее"}))
        # Потолок на проход: письмо, которому некуда идти, стоит нам одного
        # запроса, а не отправки. 40 партий по batch — с запасом на сегодняшнюю
        # очередь и без риска крутиться вечно.
        for _ in range(40):
            try:
                claimed = self.store.claim_approved_due(
                    now=now, limit=self.batch, skip_ids=разобранные,
                    skip_campaigns=набрано)
            except TypeError:"""),
        ("""            for i, m in enumerate(claimed):
                if out["sent"] >= self.batch:
                    # Партия набрана. Остаток этой десятки уже помечен
                    # 'sending' — вернуть в очередь, иначе письма зависнут.
                    for лишнее in claimed[i:]:
                        with suppress(Exception):
                            self.store.release_message(лишнее.id)
                    break
                разобранные.add(m.id)
                try:
                    self._send_one(m, win, now, out)""",
         """            for m in claimed:
                нап = напр_камп.get(getattr(m, "campaign_id", None), "прочее")
                разобранные.add(m.id)
                if по_напр.get(нап, 0) >= self.batch:
                    # Партия этого направления набрана: письмо (уже 'sending')
                    # вернуть в очередь, его кампании в проходе больше не брать.
                    набрано |= {к for к, н in напр_камп.items() if н == нап}
                    with suppress(Exception):
                        self.store.release_message(m.id)
                    continue
                было = out["sent"]
                try:
                    self._send_one(m, win, now, out)"""),
        ("""                    out["failed"] += 1
            if out["sent"] >= self.batch:
                break
        if out["released"] and not out["sent"]:""",
         """                    out["failed"] += 1
                if out["sent"] > было:
                    по_напр[нап] = по_напр.get(нап, 0) + 1
            if out["sent"] >= self.batch * всего_напр:
                break
        if out["released"] and not out["sent"]:"""),
        ("""    def _send_one(self, m: Any, win: dict, now: datetime, out: dict) -> None:""",
         """    def _napravleniya_kampaniy(self) -> dict:
        \"\"\"{campaign_id: 'kc' | 'meyer' | 'прочее'} по сегменту кампании
        (НАПРАВЛЕНИЯ-22.10). Сбой — пустой словарь: всё идёт как «прочее»,
        то есть одной общей партией, как было до правки.\"\"\"
        карта: dict = {}
        try:
            from sender.company_card import campaign_division
            for camp in self.store.list_campaigns():
                with suppress(Exception):
                    карта[int(camp.id)] = campaign_division(camp) or "прочее"
        except Exception:  # noqa: BLE001
            logger.exception("auto_send: направления кампаний не прочитались")
        return карта

    def _send_one(self, m: Any, win: dict, now: datetime, out: dict) -> None:"""),
    ],
}

if "--otkat" in sys.argv:
    for п in (STORE, AUTO):
        б = sorted(glob.glob(п + ".bak-napr-*"))
        if б:
            shutil.copy2(б[-1], п)
            print("откат:", п, "<-", б[-1])
    print("=== НАПРАВЛЕНИЯ: ОТКАТ (нужен Restart-Service SenderPanel -Force) ===")
    sys.exit(0)

тексты = {п: io.open(п, encoding="utf-8").read() for п in (STORE, AUTO)}
if all(МЕТКА in т for т in тексты.values()):
    print("=== НАПРАВЛЕНИЯ: УЖЕ БЫЛО ===")
    sys.exit(0)
for п, пары in ПРАВКИ.items():
    for было, _ in пары:
        н = тексты[п].count(было)
        if н != 1:
            print("якорь в %s найден %d раз: %r" % (os.path.basename(п), н, было[:100]))
            print("=== НАПРАВЛЕНИЯ: НЕ ПРИМЕНЕНО ===")
            sys.exit(0)
новые = {}
for п, пары in ПРАВКИ.items():
    т = тексты[п]
    for было, стало in пары:
        т = т.replace(было, стало)
    новые[п] = т
if "--primenit" not in sys.argv:
    print("якоря на месте, сухой прогон. Применить — --primenit")
    sys.exit(0)
метка_вр = int(time.time())
бэкапы = {}
for п in новые:
    бэкапы[п] = п + ".bak-napr-%d" % метка_вр
    shutil.copy2(п, бэкапы[п])
try:
    for п, т in новые.items():
        io.open(п, "w", encoding="utf-8").write(т)
        py_compile.compile(п, doraise=True)
except Exception as е:  # noqa: BLE001
    for п, б in бэкапы.items():
        shutil.copy2(б, п)
    print("сбой, откат обоих: %s" % е)
    print("=== НАПРАВЛЕНИЯ: ОТКАТ ===")
    sys.exit(0)
print("бэкапы:", list(бэкапы.values()))
print("=== НАПРАВЛЕНИЯ: ПРИМЕНЕНО (нужен Restart-Service SenderPanel -Force) ===")
