# -*- coding: utf-8 -*-
"""Положить в очередь письмо, написанное РУКАМИ, на указанный адрес.

Владелец 18.08: «в ответах давали другие емейлы, что по ним обращаться, и
один был в отпуске - напиши им письма вручную и отправь без окна отправки».

Текст письма пишу я, не генератор: это ответ на конкретную переадресацию, и
в нём надо сослаться на того, кто её сделал. Отправку делает оператор из
панели - при confirm.live_send подтверждение уходит немедленно, окно
отправки на ручную отправку не распространяется.

Получателя ищем по адресу; если такого нет - заводим строку, копируя фирму,
ИНН и регион у уже известного получателя той же компании. Пишем в поле
kind='outbound', кампания та же.

    python zapusk_svoego_skripta.py ops/pismo_rukami_v_ochered.py           # показать
    python zapusk_svoego_skripta.py ops/pismo_rukami_v_ochered.py --класть
"""
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

КЛАСТЬ = "--класть" in sys.argv

ПИСЬМА = [
    {
        "инн": "7816693698",
        "кому": "info@hoger.pro",
        "кампания": 10,
        "тема": "Вопрос по компрессорному парку в «Хёгер»",
        "тело": """Добрый день!

Виталий Перов передал ваш адрес: вопрос по компрессорному оборудованию не его направления.

На сайте у вас токарные станки с ЧПУ и гидроабразивные установки, собственный цех больше двух тысяч квадратных метров. Станочный парк такого масштаба завязан на сжатый воздух, и требования к его чистоте и стабильности давления обычно выше, чем к общезаводской магистрали.

Я веду направление компрессорного оборудования в Компрессор Центре. Подскажите, актуален ли для вас сейчас вопрос обновления или расширения компрессорного парка?

Если тема неактуальна, буду признателен за короткий ответ, чтобы в дальнейшем вас не отвлекать.

С уважением,""",
    },
    {
        "инн": "9909125356",
        "кому": "belyaevse@jinr.ru",
        "кампания": 10,
        "тема": "Вопрос по сжатому воздуху и азоту в ОИЯИ",
        "тело": """Добрый день, Станислав Евгеньевич!

Николай Калинин передал ваши контакты по вопросу сжатого воздуха и азота.

У института ускорительные комплексы NICA и Нуклотрон, циклотроны U-400 и U-400M, реактор ИБР-2. На таких установках воздух и азот идут как рабочая среда, и критична не мощность, а точка росы и стабильное давление на всю длину измерительного цикла.

Я веду направление компрессорного оборудования и генерации азота в Компрессор Центре. Подскажите, актуален ли сейчас вопрос обновления или расширения системы сжатого воздуха и азота на площадках института?

Если тема неактуальна, буду признателен за короткий ответ, чтобы в дальнейшем вас не отвлекать.

С уважением,""",
    },
]

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
сейчас = datetime.now(timezone.utc).isoformat()

for п in ПИСЬМА:
    адрес = п["кому"].strip().lower()
    with store._lock:
        есть = store._conn.execute(
            "SELECT id, company_name FROM recipients WHERE lower(email)=?",
            (адрес,)).fetchone()
        донор = store._conn.execute(
            "SELECT id, company_name, inn, segment, region, domain, "
            "       mx_provider, tz FROM recipients WHERE inn=? LIMIT 1",
            (п["инн"],)).fetchone()
        письмо_есть = store._conn.execute(
            "SELECT id, status FROM confirm_reviews WHERE lower(email)=? "
            "ORDER BY id DESC LIMIT 1", (адрес,)).fetchone()
        стоп = store._conn.execute(
            "SELECT reason FROM suppression WHERE lower(value)=?",
            (адрес,)).fetchone()
    print(f"\n{адрес}  (ИНН {п['инн']})")
    print(f"  получатель в базе: {tuple(есть) if есть else 'НЕТ, заведу'}")
    print(f"  донор карточки:    {donor[1] if (donor := донор) else 'НЕТ'}")
    print(f"  письмо на этот адрес: "
          f"{tuple(письмо_есть) if письмо_есть else 'нет'}")
    print(f"  стоп-лист: {стоп[0] if стоп else 'чисто'}")
    п["_есть"], п["_донор"], п["_стоп"] = есть, донор, стоп

if not КЛАСТЬ:
    print("\nсухой прогон: в очередь ничего не положено. Класть — --класть")
    raise SystemExit(0)

for п in ПИСЬМА:
    адрес = п["кому"].strip().lower()
    if п["_стоп"]:
        print(f"{адрес}: В СТОП-ЛИСТЕ ({п['_стоп'][0]}) — не пишу")
        continue
    донор = п["_донор"]
    if донор is None:
        print(f"{адрес}: нет донора карточки — пропускаю")
        continue
    rid = п["_есть"][0] if п["_есть"] else None
    if rid is None:
        with store._lock:
            cur = store._conn.execute(
                "INSERT INTO recipients (email, company_name, inn, segment, "
                "region, domain, mx_provider, tz, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (адрес, донор[1], донор[2], донор[3], донор[4],
                 адрес.split("@")[-1], донор[6], донор[7], сейчас, сейчас))
            rid = cur.lastrowid
            store._conn.commit()
        print(f"{адрес}: заведён получатель #{rid}")
    # Письму нужна строка в messages, иначе подтверждение падает «нет
    # message_id — нечего отправлять»: очередь подтверждения хранит текст, а
    # отправка работает с сообщением. Делаем тем же helper-ом, что и
    # генерация, со статусом pending_review — авто-поток такое не подхватит.
    mid = None
    try:
        from sender.ai_quota import build_ai_quota
        _q = build_ai_quota(store, cfg)
        mid, _step, _почему = _q._ensure_message(int(п["кампания"]), int(rid))
        if not mid:
            print(f"{адрес}: сообщение не завелось — {_почему}")
    except Exception as ex:                                      # noqa: BLE001
        print(f"{адрес}: сообщение не завелось — {type(ex).__name__} "
              f"{str(ex)[:120]}")
    ключ = f"{п['инн']}|{адрес}|{п['кампания']}"
    панель = json.dumps({"letter_division": "kc",
                         "написано": "оператором вручную 18.08 по "
                                     "переадресации из ответа"},
                        ensure_ascii=False)
    with store._lock:
        try:
            cur = store._conn.execute(
                "INSERT INTO confirm_reviews (dedup_key, campaign_id, "
                "recipient_id, message_id, inn, email, subject, body, "
                "panel_json, status, kind, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,'pending','outbound',?,?)",
                (ключ, п["кампания"], rid, mid, п["инн"], адрес, п["тема"],
                 п["тело"], панель, сейчас, сейчас))
            store._conn.commit()
            print(f"{адрес}: письмо в очереди #{cur.lastrowid}")
        except Exception as ex:                                  # noqa: BLE001
            print(f"{адрес}: не легло — {str(ex)[:140]}")
