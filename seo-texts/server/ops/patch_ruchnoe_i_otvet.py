# -*- coding: utf-8 -*-
"""Две правки в api/app.py по якорям.

1. /confirm/novoe заводит письмо в messages — без него approve падает
   «нет message_id — нечего отправлять», и кнопка «новое письмо» доводит
   до очереди, но не до отправки.
2. Ответ из карточки лида уходит СРАЗУ (владелец 31.08: «сделай чтобы
   сразу в ветке если пишешь ответ улетало»). Текст пишет оператор, там
   нечего подтверждать вторым нажатием. Заслоны отписки и жалобы остаются:
   они внутри approve.

Каталог общий с другими сессиями, поэтому правим только по якорям, с
.bak, проверкой компиляции и откатом.
"""
import io
import os
import py_compile
import sys
import time

ФАЙЛ = r"C:\sender\sender\api\app.py"
ПРИМЕНИТЬ = "--primenit" in sys.argv

ПАРЫ = [
    # --- 1. ручное письмо получает строку в messages ---------------------
    ('''        if ящик:
            with suppress(Exception):
                deps.confirm.set_mailbox(int(rid), ящик, operator=p.username)
        _проверить_срочно(адрес)''',
     '''        if ящик:
            with suppress(Exception):
                deps.confirm.set_mailbox(int(rid), ящик, operator=p.username)
        # ПИСЬМО В messages, ИНАЧЕ ОТПРАВИТЬ ЕГО НЕЛЬЗЯ. approve() у исходящих
        # первым делом спрашивает message_id и без него отказывает: «нечего
        # отправлять». Генерация эту строку заводит сама, а ручное письмо
        # приходило в очередь без неё — то есть кнопка доводила до очереди и
        # упиралась на отправке. Кампанию берём из запроса, иначе по
        # направлению выбранного ящика (kc -> 10, meyer -> 11).
        _mid_ruchnogo, _pochemu_net = None, ""
        try:
            _camp = body.campaign_id
            if not _camp and ящик:
                _napr = ""
                for _mb in deps.config.mailboxes():
                    if _mb.mailbox_id == ящик:
                        _napr = str(getattr(_mb, "division", "") or "")
                        break
                _camp = 11 if _napr.startswith("meyer") else 10
            if _camp and новый_id:
                from sender.ai_quota import AiQuota
                _q = AiQuota(deps.store,
                             db_path=str(deps.config.get("service.db_path",
                                                         "sender.db")),
                             config=deps.config)
                _mid_ruchnogo, _st, _pochemu_net = _q._ensure_message(
                    int(_camp), int(новый_id))
                if _mid_ruchnogo:
                    deps.store.confirm_set_message(int(rid), int(_mid_ruchnogo))
            else:
                _pochemu_net = "нет кампании или строки получателя"
        except Exception as _e:  # noqa: BLE001 - письмо уже лежит в очереди
            _pochemu_net = str(_e)[:120]
        _проверить_срочно(адрес)'''),
    ('''        return {"ok": True, "id": rid, "sozdano": создано, "email": адрес,
                "mailbox_id": ящик, "recipient_id": новый_id}''',
     '''        return {"ok": True, "id": rid, "sozdano": создано, "email": адрес,
                "mailbox_id": ящик, "recipient_id": новый_id,
                "message_id": _mid_ruchnogo, "pochemu_bez_pisma": _pochemu_net}'''),
    # --- 2. ответ в ветке уходит сразу ------------------------------------
    ('''        if res.status == "skipped":
            raise HTTPException(status_code=409,
                                detail=f"заслон: {res.reason or 'skipped'}")
        return {"ok": True, "review_id": res.review_id, "created": res.created}''',
     '''        if res.status == "skipped":
            raise HTTPException(status_code=409,
                                detail=f"заслон: {res.reason or 'skipped'}")
        # ОТВЕТ В ВЕТКЕ УХОДИТ СРАЗУ (владелец 31.08: «сделай чтобы сразу в
        # ветке если пишешь ответ улетало»). Текст написан оператором прямо
        # здесь, в карточке лида: подтверждать его вторым нажатием в очереди
        # незачем - это тот же человек и то же решение. Заслоны никуда не
        # делись, они внутри approve: отписка, жалоба, стоп-лист.
        # Не ушло - черновик остаётся в очереди, и причина видна в ответе.
        _ushlo, _pochemu = False, ""
        try:
            _ushlo = bool(deps.confirm.approve(int(res.review_id),
                                               operator=p.username,
                                               actor_user_id=p.user_id))
        except Exception as _e:  # noqa: BLE001 - черновик остаётся в очереди
            _pochemu = str(_e)[:160]
        return {"ok": True, "review_id": res.review_id, "created": res.created,
                "otpravleno": _ushlo, "pochemu_net": _pochemu}'''),
]

т = io.open(ФАЙЛ, encoding="utf-8").read()
print("файл: %d Б, строк %d" % (len(т.encode("utf-8")), len(т.splitlines())))
ошибок = 0
for i, (стар, нов) in enumerate(ПАРЫ, 1):
    n = т.count(стар)
    print("   якорь %d: вхождений %d %s" % (i, n, "ок" if n == 1 else "ОТКАЗ"))
    if n != 1:
        ошибок += 1
if ошибок:
    print("\nякоря не уникальны — не трогаю файл")
    raise SystemExit(1)

новый = т
for стар, нов in ПАРЫ:
    новый = новый.replace(стар, нов, 1)
print("\nстанет строк: %d (было %d)" % (len(новый.splitlines()),
                                        len(т.splitlines())))
if not ПРИМЕНИТЬ:
    print("\n[сухой прогон] применить — с ключом --primenit")
    raise SystemExit(0)

запас = "%s.bak-%d" % (ФАЙЛ, int(time.time()))
io.open(запас, "w", encoding="utf-8").write(т)
print("бэкап: %s" % запас)
with io.open(ФАЙЛ, "w", encoding="utf-8") as f:
    f.write(новый)
    f.flush()
    os.fsync(f.fileno())
try:
    py_compile.compile(ФАЙЛ, doraise=True)
    print("py_compile: ок")
except Exception as e:                                        # noqa: BLE001
    io.open(ФАЙЛ, "w", encoding="utf-8").write(т)
    print("КОМПИЛЯЦИЯ УПАЛА, откатил: %s" % str(e)[:200])
    raise SystemExit(1)
print("\n=== ИТОГ ===")
print("правки на месте. Нужен перезапуск службы, чтобы панель их подхватила.")
