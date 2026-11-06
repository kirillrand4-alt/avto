# -*- coding: utf-8 -*-
"""Владелец 06.11: образцы писем КЦ «по имени» (заход «планы и бюджеты на год»,
заказчики РУСАЛ/РЖД/Северсталь/Алроса), уникализация: варианты блоков + одна фраза
про компанию от модели + перемешанные заказчики. Только показ, в базу не пишет.
    obrazcy_imennye_kc.py [N=10]"""
import io, json, random, re, sqlite3, sys
sys.path.insert(0, r"C:\sender"); sys.path.insert(0, r"C:\sender\server")
from sender.config import Config  # noqa: E402
import gen_provider as GP          # noqa: E402
N = next((int(a) for a in sys.argv[1:] if a.isdigit()), 10)
random.seed(611)
s = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
e = sqlite3.connect("file:C:\\sender\\enrich.db?mode=ro", uri=True, timeout=30)
o = sqlite3.connect("file:C:\\sender\\obzvon-index.db?mode=ro", uri=True, timeout=30)
кц = {str(i) for i, d in o.execute("SELECT inn, division FROM obzvon") if "kc" in str(d or "").lower()}
недавно = {str(r[0]) for r in s.execute("SELECT DISTINCT inn FROM send_log WHERE outcome='sent' AND ts>=datetime('now','-21 days') AND inn IS NOT NULL")}
ответ = {str(r[0]) for r in s.execute("SELECT DISTINCT r.inn FROM events e JOIN recipients r ON r.id=e.recipient_id WHERE e.event_type IN ('reply','complaint','unsubscribe')")}
стоп = {v.lower() for _, v in s.execute("SELECT scope, value FROM suppression")}
мёртв = {r[0].lower() for r in s.execute("SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX','неясно','отказ пробе')")}
ТЕХ = r"механик|энергетик|главн\w* инженер|техн\w* директор|начальник (цеха|производства)|технолог|ремонт|эксплуатац"
канд = {}
for inn, person, post, role, em in e.execute("SELECT inn, person, COALESCE(zahod_rol,''), COALESCE(role,''), email FROM emails WHERE person IS NOT NULL AND trim(person)!='' AND imya_ok='1' AND email IS NOT NULL"):
    inn, em = str(inn), em.lower()
    if inn not in кц or inn in ответ or inn in недавно or em in стоп or inn in стоп or em in мёртв:
        continue
    тех = bool(re.search(ТЕХ, post + " " + role, re.I))
    if inn not in канд or (тех and not канд[inn][3]):
        канд[inn] = (person.strip(), em, (post or role).strip(), тех)
выбор = random.sample(sorted(канд), min(N, len(канд)))
def обращение(fio):
    ч = fio.split()
    if len(ч) >= 3: return ч[1] + " " + ч[2]
    if len(ч) == 2: return ч[1] if ч[1][-2:] not in ("ов", "ев", "ин", "ва", "на") else ч[0]
    return ч[0]
ПОВОД = ["Сейчас на крупных предприятиях формируют планы модернизации и бюджеты на следующий год, поэтому и пишу.",
         "Пишу сейчас, потому что в ноябре–декабре предприятия обычно закладывают модернизацию и бюджеты на следующий год.",
         "Многие производства как раз сейчас верстают бюджеты на следующий год, поэтому решил написать заранее.",
         "Конец года - время, когда планируют модернизацию на следующий год, поэтому пишу сейчас."]
ОХВАТ = ["Ведём проекты по сжатому воздуху на крупных производствах: от отдельного компрессора до модульной станции с осушкой и генерацией азота.",
         "Занимаемся сжатым воздухом на производствах под ключ: от одного компрессора до модульной станции с осушкой и генерацией азота.",
         "Делаем проекты по сжатому воздуху: от замены одного компрессора до модульной компрессорной станции с осушкой и азотом."]
ЗАК = ["РУСАЛ", "РЖД", "«Северсталь»", "«Алроса»"]
ЗАК_ФР = ["Среди заказчиков {z}.", "Работали с {z}.", "Среди наших заказчиков - {z}."]
СЕРВИС = ["У нас свой сервисный центр и свои инженеры.", "Сервис и инженеры - свои.", "Обслуживание ведут наши инженеры, сервисный центр свой."]
ВОПРОС = ["Скажите, в планах на ближайшие 4 месяца есть модернизация компрессорной или расширение?",
          "Подскажите, планируете ли в ближайшие месяцы модернизацию или расширение компрессорной?",
          "Есть ли в планах на ближайшие месяцы обновление компрессорного парка или расширение?"]
ПЕРЕСЛАТЬ = ["Если этим занимается ваш главный механик или энергетик, буду благодарен, если перешлёте ему письмо.",
             "Если вопрос не по вашей части, перешлите, пожалуйста, письмо главному механику или энергетику.",
             "Если это зона главного инженера или механика, буду признателен, если передадите ему письмо."]
ящики = [m for m in Config.load(r"C:\sender\sender.yaml").mailboxes() if str(getattr(m, "division", "")) == "kc"]
ЗАДАНИЕ = """Для каждой компании напиши ОДНУ фразу (до 22 слов) для холодного письма поставщика компрессоров:
где на ИХ производстве нужен сжатый воздух (по виду деятельности и продукции). Без цифр, без марок, без «мы»,
без выдумок: если деятельность неясна - напиши общую фразу про производство. Без длинных тире.
{firmy}
Ответ - СТРОГО JSON: {{"f": [{{"n": 1, "t": "..."}}]}}"""
строки = []
for i, inn in enumerate(выбор, 1):
    r = e.execute("SELECT name, okved, substr(COALESCE(activity,''),1,300) FROM companies WHERE inn=?", (inn,)).fetchone() or ("", "", "")
    строки.append("%d. %s; ОКВЭД %s; %s" % (i, r[0], r[1], r[2]))
м = GP._raw_stream([{"role": "user", "content": ЗАДАНИЕ.replace("{firmy}", "\n".join(строки)).replace("{{", "{").replace("}}", "}")}],
                   "claude-sonnet-4-6", 2000, thinking=False, effort="low")
т = м if isinstance(м, str) else "".join(getattr(b, "text", "") for b in getattr(м, "content", []) or [])
фразы = {int(x["n"]): x["t"] for x in json.JSONDecoder(strict=False).raw_decode(т[т.find("{"):])[0].get("f", [])}
вых = []
for i, inn in enumerate(выбор, 1):
    fio, em, должн, тех = канд[inn]
    имя_комп = (e.execute("SELECT name FROM companies WHERE inn=?", (inn,)).fetchone() or [""])[0]
    mb = random.choice(ящики)
    менеджер = (str(getattr(mb, "from_name", "") or "").split(",")[0].split() or ["Сергей"])[0]
    з = random.sample(ЗАК, 3)
    абз = [обращение(fio) + ", добрый день! Меня зовут " + менеджер + ", я из Компрессор Центра. " + random.choice(ПОВОД),
           (фразы.get(i, "") + " " if фразы.get(i) else "") + random.choice(ОХВАТ) + " " + random.choice(ЗАК_ФР).format(z=", ".join(з[:-1]) + " и " + з[-1]) + " " + random.choice(СЕРВИС),
           random.choice(ВОПРОС) + ("" if тех else " " + random.choice(ПЕРЕСЛАТЬ))]
    вых.append("=== %d. %s | %s (%s) | %s | с ящика %s\n\n%s\n" % (i, имя_комп, fio, должн or "должность не указана", em, mb.mailbox_id, "\n\n".join(абз)))
т = "\n".join(вых)
print(т)
io.open(r"C:\sender\_ops\obrazcy-imennye-kc.txt", "w", encoding="utf-8").write(т)
