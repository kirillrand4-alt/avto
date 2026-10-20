# -*- coding: utf-8 -*-
"""Письма по переадресациям из ответов 20.10 — в «Подтвердить отправку»
(отправляет оператор кнопкой в панели). Владелец 20.10:
  * Постак: i.litvinova@bong.ru дала p.osipov@bong.ru (рук. тех. службы);
  * ИНКОМ: Христич посоветовал головное предприятие — завод АКОМ (Жигулёвск),
    на сайте akom.su только общий адрес desk@akom.su.
Механика — как pismo_rukami_v_ochered.py (18.08): получатель (донор карточки по
адресу исходного письма, иначе — новая строка), сообщение pending_review через
_ensure_message, карточка confirm_reviews pending. Кампания 17 «КЦ-1 август».

    pisma_rukami_2010.py [--klast]"""
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

КЛАСТЬ = "--klast" in sys.argv
КАМП = 17
ПИСЬМА = [
    {
        "донор": "i.litvinova@bong.ru",
        "кому": "p.osipov@bong.ru",
        "контакт": "Осипов Павел Юрьевич",
        "тема": "Вопрос по компрессорному парку в «Постак»",
        "тело": """Добрый день, Павел Юрьевич!

Ирина Литвинова подсказала, что вопросы компрессорного оборудования у вас ведёт техническая служба, поэтому пишу напрямую.

Смотрел производство «Постак» - конвертоделательные и печатные линии работают на сжатом воздухе: толкатели, воздушные подушки, обдув полотна. При круглосуточной работе компрессорный парк обычно первым оказывается под нагрузкой.

Я веду направление компрессорного оборудования в Компрессор Центре. Подскажите, актуален ли сейчас вопрос обновления или расширения компрессорного парка? Если да - под какие задачи? Буду рад провести пневмоаудит и подобрать оптимальный вариант.

Если тема сейчас неактуальна, буду признателен за короткий ответ, чтобы в дальнейшем вас не отвлекать.

С уважением,""",
    },
    {
        "донор": None,
        "кому": "desk@akom.su",
        "компания": "АО «АКОМ им. Н.М. Игнатьева»",
        "регион": "Самарская область",
        "tz": "Europe/Samara",
        "тема": "Для главного механика: вопрос по компрессорному парку «АКОМ»",
        "тело": """Добрый день!

Дмитрий Христич из «Индустриальной компании ИНКОМ» посоветовал обратиться в головное предприятие, поэтому пишу вам.

На производстве стартерных аккумуляторов сжатый воздух идёт сразу на несколько участков: пневматика сборочных линий, продувка, испытания. При таком объёме выпуска компрессорный парк работает почти без остановок, и замену или расширение обычно планируют заранее.

Я веду направление компрессорного оборудования в Компрессор Центре - в том числе центробежные машины и станции под ключ для крупных производств. Подскажите, актуален ли сейчас вопрос обновления или расширения компрессорного парка на заводе?

Если письмо попало не по адресу, буду благодарен за контакт главного механика или энергетика - обращусь напрямую.

Если тема сейчас неактуальна, буду признателен за короткий ответ, чтобы в дальнейшем вас не отвлекать.

С уважением,""",
    },
]
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
сейчас = datetime.now(timezone.utc).isoformat()
к = store._conn
for п in ПИСЬМА:
    адрес = п["кому"].lower()
    п["_есть"] = к.execute("SELECT id FROM recipients WHERE lower(email)=?", (адрес,)).fetchone()
    п["_донор"] = к.execute("SELECT id, company_name, inn, segment, region, domain, mx_provider, tz, extra_json "
                            "FROM recipients WHERE lower(email)=?", (п["донор"],)).fetchone() if п["донор"] else None
    п["_стоп"] = к.execute("SELECT reason FROM suppression WHERE lower(value)=?", (адрес,)).fetchone()
    п["_было"] = к.execute("SELECT id, status FROM confirm_reviews WHERE lower(email)=? ORDER BY id DESC LIMIT 1", (адрес,)).fetchone()
    print("\n%s | получатель: %s | донор: %s | стоп: %s | карточка была: %s" % (
        адрес, tuple(п["_есть"]) if п["_есть"] else "нет", п["_донор"][1] if п["_донор"] else п.get("компания"),
        п["_стоп"][0] if п["_стоп"] else "чисто", tuple(п["_было"]) if п["_было"] else "нет"))
    print("Тема:", п["тема"])
if not КЛАСТЬ:
    print("\nсухой прогон. Класть — --klast")
    raise SystemExit(0)
from sender.ai_quota import build_ai_quota  # noqa: E402
q = build_ai_quota(store, cfg)
for п in ПИСЬМА:
    адрес = п["кому"].lower()
    if п["_стоп"] or п["_было"]:
        print(адрес, ": пропуск (стоп-лист или уже есть карточка)")
        continue
    д = п["_донор"]
    инн = д[2] if д else None
    if п["_есть"]:
        rid = п["_есть"][0]
    else:
        with store._lock:
            cur = к.execute(
                "INSERT INTO recipients (email, company_name, inn, segment, region, domain, mx_provider, tz, contact_name, "
                "source, extra_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (адрес, д[1] if д else п["компания"], инн, (д[3] if д else None) or "кц", д[4] if д else п["регион"],
                 адрес.split("@")[-1], д[6] if д else None, (д[7] if д else п["tz"]) or "Europe/Moscow",
                 п.get("контакт"), "переадресация-руками",
                 json.dumps({"target_division": "kc", "pereadresaciya": п["донор"] or "ИНКОМ (Христич) -> головное АКОМ"},
                            ensure_ascii=False), сейчас, сейчас))
            rid = cur.lastrowid
            к.commit()
    mid, _шаг, почему = q._ensure_message(КАМП, int(rid))
    if not mid:
        print(адрес, ": сообщение не завелось —", почему)
        continue
    панель = json.dumps({"letter_division": "kc", "написано": "вручную 20.10 по переадресации из ответа"}, ensure_ascii=False)
    with store._lock:
        cur = к.execute(
            "INSERT INTO confirm_reviews (dedup_key, campaign_id, recipient_id, message_id, inn, email, subject, body, "
            "panel_json, status, kind, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,'pending','outbound',?,?)",
            ("%s|%s|%d" % (инн or "", адрес, КАМП), КАМП, rid, mid, инн, адрес, п["тема"], п["тело"], панель, сейчас, сейчас))
        к.commit()
    print(адрес, ": в «Подтвердить отправку», карточка #%d" % cur.lastrowid)
