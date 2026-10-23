# -*- coding: utf-8 -*-
"""Другой адрес той же компании — через 3 дня (владелец 23.10: «сделай правку,
чтобы я мог отправить письмо той же компании, но на другой адрес через 3 дня»).

1) infopanel.povtor_toy_zhe_napr — флаг «контакт <30 дн тем же направлением»
   по прошлым письмам на ДРУГОЙ адрес компании держится 3 дня, а не 30; по
   письмам на ЭТОТ ЖЕ адрес — как было, 30 дней.
2) auto_send — заслон «уже писали»: если ЭТОМУ адресу не писали никогда, а
   компании (ИНН) писали на другой адрес — письмо уходит, когда с последней
   отправки компании прошло 3 дня; раньше — переносится на «последняя + 3 дня».
   Тому же адресу — через 30 дней после прошлого письма на него, если
   компания нам не отвечала (владелец 23.10: «нет, тут 30 дней оставь»).

Правка двух файлов по якорям: бэкап .bak-3dnya-<время>, py_compile, откат
обоих при сбое; --otkat — из последних бэкапов. Нужен Restart-Service.
    lesenka_3dnya.py [--primenit | --otkat] [--koren=<папка>]"""
import glob
import io
import os
import py_compile
import shutil
import sys
import time

КОРЕНЬ = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--koren=")), r"C:\sender\sender")
INFO = os.path.join(КОРЕНЬ, "infopanel.py")
AUTO = os.path.join(КОРЕНЬ, "auto_send.py")
МЕТКА = "ЛЕСЕНКА-3ДНЯ-23.10"
ПРАВКИ = {
    INFO: [
        ("""    _когда = povtor_toy_zhe_napr(store, history, body)""",
         """    _когда = povtor_toy_zhe_napr(store, history, body, email=email)"""),
        ("""def povtor_toy_zhe_napr(store, history, body, dney: int = 30) -> Optional[str]:
    \"\"\"Дата последней отправки ТЕМ ЖЕ направлением в окне dney — или None.\"\"\"
    from sender.napravlenie_pisma import po_leksike
    моё = po_leksike(body)
    граница = datetime.now(timezone.utc).timestamp() - dney * 86400""",
         """def povtor_toy_zhe_napr(store, history, body, dney: int = 30,
                        email: Optional[str] = None,
                        dney_drugoy: int = 3) -> Optional[str]:
    \"\"\"Дата последней отправки ТЕМ ЖЕ направлением в окне dney — или None.

    ЛЕСЕНКА-3ДНЯ-23.10 (владелец: «отправить письмо той же компании, но на
    другой адрес через 3 дня»): письмо, ушедшее на ДРУГОЙ адрес компании,
    держит флаг dney_drugoy дней; на этот же адрес — dney, как раньше.\"\"\"
    from sender.napravlenie_pisma import po_leksike
    моё = po_leksike(body)
    граница = datetime.now(timezone.utc).timestamp() - dney * 86400
    граница_др = datetime.now(timezone.utc).timestamp() - dney_drugoy * 86400
    мой_адрес = str(email or "").strip().lower()"""),
        ("""        if ts.timestamp() < граница:
            continue
        его = _napr_kampanii(store, it.get("campaign_id"), it.get("subject"))""",
         """        другой = bool(мой_адрес) and str(it.get("email") or "").strip().lower() != мой_адрес
        if ts.timestamp() < (граница_др if другой else граница):
            continue
        его = _napr_kampanii(store, it.get("campaign_id"), it.get("subject"))"""),
    ],
    AUTO: [
        ("""            if _копия is None:
                след = {}
            else:""",
         """            # ДРУГОЙ АДРЕС ТОЙ ЖЕ КОМПАНИИ — ЧЕРЕЗ 3 ДНЯ (ЛЕСЕНКА-3ДНЯ-23.10,
            # владелец: «отправить письмо той же компании, но на другой адрес
            # через 3 дня»). Этому адресу не писали никогда, компании писали на
            # другой: прошло 3 дня — шлём, нет — переносим на «последняя + 3».
            # Тот же адрес — через 30 дней (владелец 23.10: «нет, тут 30 дней
            # оставь»), если компания нам не отвечала.
            if _копия is False and почта:
                _фл = self.store.sent_flags(emails=[почта], inns=[инн] if инн else None) or {}
                if (_фл.get(почта) or {}).get("ever"):
                    _посл_а = self.store.last_contact(email=почта)
                    _когда_а = _parse_iso((_посл_а or {}).get("ts"))
                    if _когда_а is not None and now - _когда_а >= timedelta(days=30):
                        from sender.confirm import ConfirmSend
                        if not ConfirmSend(self.config, self.store)._otvechali(инн):
                            _копия = None   # 30 дней прошло: заслон не применяем
                elif инн and (_фл.get(инн) or {}).get("ever"):
                    _посл_к = self.store.last_contact(inn=инн)
                    _когда = _parse_iso((_посл_к or {}).get("ts"))
                    if _когда is not None and now - _когда < timedelta(days=3):
                        self.store.release_message(m.id)
                        self.store.reschedule_message(m.id, _когда + timedelta(days=3))
                        out["released"] += 1
                        return
                    _копия = True
            if _копия is None:
                след = {}
            else:"""),
    ],
}
if "--otkat" in sys.argv:
    for п in (INFO, AUTO):
        б = sorted(glob.glob(п + ".bak-3dnya-*"))
        if б:
            shutil.copy2(б[-1], п)
            print("откат:", п, "<-", б[-1])
    print("=== 3 ДНЯ: ОТКАТ (нужен рестарт) ===")
    sys.exit(0)
тексты = {п: io.open(п, encoding="utf-8").read() for п in ПРАВКИ}
if all(МЕТКА in т for т in тексты.values()):
    print("=== 3 ДНЯ: УЖЕ БЫЛО ===")
    sys.exit(0)
for п, пары in ПРАВКИ.items():
    for было, _ in пары:
        if тексты[п].count(было) != 1:
            print("якорь в %s найден %d раз: %r" % (os.path.basename(п), тексты[п].count(было), было[:90]))
            print("=== 3 ДНЯ: НЕ ПРИМЕНЕНО ===")
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
метка = int(time.time())
бэкапы = {п: п + ".bak-3dnya-%d" % метка for п in новые}
for п, б in бэкапы.items():
    shutil.copy2(п, б)
try:
    for п, т in новые.items():
        io.open(п, "w", encoding="utf-8").write(т)
        py_compile.compile(п, doraise=True)
except Exception as е:  # noqa: BLE001
    for п, б in бэкапы.items():
        shutil.copy2(б, п)
    print("сбой, откат обоих: %s" % е)
    sys.exit(0)
print("бэкапы:", list(бэкапы.values()))
print("=== 3 ДНЯ: ПРИМЕНЕНО (нужен Restart-Service SenderPanel -Force) ===")
