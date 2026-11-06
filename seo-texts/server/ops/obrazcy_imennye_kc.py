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
ТЕХ = r"техдиректор|тех\.?\s*директор|механик|энергетик|главн\w* инженер|гл\.?\s*инж|гл\.?\s*мех|гл\.?\s*энерг|техн\w* директор|начальник (цеха|производства)|технолог|ремонт|эксплуатац"
ИМЕНА = set("""александр алексей анатолий андрей антон аркадий артём артем борис вадим валентин валерий василий виктор виталий владимир владислав вячеслав геннадий георгий глеб григорий даниил денис дмитрий евгений егор иван игорь илья кирилл константин леонид максим марат михаил никита николай олег павел пётр петр роман руслан рустам сергей станислав степан тимур фёдор федор эдуард юрий ярослав
александра алина алла анастасия анна антонина валентина валерия вера виктория галина дарья евгения екатерина елена жанна зинаида зоя инна ирина карина кристина лариса лидия любовь людмила маргарита марина мария надежда наталья наталия нина оксана ольга полина раиса светлана софья тамара татьяна ульяна юлия яна""".split())
def обращение(fio):
    ч = [x for x in re.split(r"\s+", fio.strip()) if x]
    if any(len(x.strip(".")) <= 2 or "." in x for x in ч):
        return None                              # одни инициалы — не обращаемся
    for i, x in enumerate(ч):                    # Имя + Отчество
        if re.search(r"(вич|вна|ична|ьич)$", x, re.I) and i > 0 and ч[i - 1].lower() in ИМЕНА:
            return ч[i - 1] + " " + x
    for x in ч:
        if x.lower() in ИМЕНА:
            return x
    return None
def отрасль_годна(inn):
    r = e.execute("SELECT COALESCE(okved,''), COALESCE(name,'') FROM companies WHERE inn=?", (inn,)).fetchone()
    if not r: return False
    ок, имя = r
    м = re.match(r"(\d{2})", ок or "")
    if not м: return False
    к = int(м.group(1))
    if re.search(r"больниц|ЦРБ|КМБ|поликлиник|медицин|клиник|санатор|школ|детск\w* сад|университет|колледж|торгов\w* дом|^ТД |\bТД\b", имя, re.I):
        return False
    return 5 <= к <= 43 or 49 <= к <= 52   # добыча, обработка, энергетика, вода, стройка, транспорт
канд = {}
for inn, person, post, role, em in e.execute("SELECT inn, person, COALESCE(zahod_rol,''), COALESCE(role,''), email FROM emails WHERE person IS NOT NULL AND trim(person)!='' AND imya_ok='1' AND email IS NOT NULL"):
    inn, em = str(inn), em.lower()
    if not re.search(r"\.(ru|рф|su|com|org|net|pro|biz|info)$", em) or em.endswith(".by"):
        continue
    if inn not in кц or not отрасль_годна(inn) or inn in ответ or inn in недавно or em in стоп or inn in стоп or em in мёртв:
        continue
    тех = bool(re.search(ТЕХ, post + " " + role, re.I))
    if not обращение(person):
        continue
    if inn not in канд or (тех and not канд[inn][3]):
        канд[inn] = (person.strip(), em, (post or role).strip(), тех)
выбор = random.sample(sorted(канд), min(N, len(канд)))
ПОВОД = ["Сейчас на крупных предприятиях формируют планы модернизации и бюджеты на следующий год, поэтому и пишу.",
         "Пишу сейчас, потому что в ноябре–декабре предприятия обычно закладывают модернизацию и бюджеты на следующий год.",
         "Многие производства как раз сейчас верстают бюджеты на следующий год, поэтому решил написать заранее.",
         "Конец года - время, когда планируют модернизацию на следующий год, поэтому пишу сейчас."]
ОХВАТ = ["Ведём проекты по сжатому воздуху на крупных производствах: от отдельного компрессора до модульной станции с осушкой и генерацией азота.",
         "Занимаемся сжатым воздухом на производствах под ключ: от одного компрессора до модульной станции с осушкой и генерацией азота.",
         "Делаем проекты по сжатому воздуху: от замены одного компрессора до модульной компрессорной станции с осушкой и азотом."]
ЗАК = ["РУСАЛ", "РЖД", "«Северсталь»", "«Алроса»"]
ЗАК_ТВ = {"РУСАЛ": "РУСАЛом", "РЖД": "РЖД", "«Северсталь»": "«Северсталью»", "«Алроса»": "«Алросой»"}
ЗАК_ФР = ["Среди заказчиков {z}.", "Работали с {zt}.", "Среди наших заказчиков - {z}."]
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
Пример фразы: «На линиях литья и упаковки пластика сжатый воздух работает в пневмоцилиндрах, обдуве форм и транспортировке гранулы.»
Ответ - СТРОГО JSON вида {{"f": [{{"n": НОМЕР, "t": "ФРАЗА"}}]}} с фразой для КАЖДОЙ компании."""
строки = []
for i, inn in enumerate(выбор, 1):
    r = e.execute("SELECT name, okved, substr(COALESCE(activity,''),1,300) FROM companies WHERE inn=?", (inn,)).fetchone() or ("", "", "")
    строки.append("%d. %s; ОКВЭД %s; %s" % (i, r[0], r[1], r[2]))
м = GP._raw_stream([{"role": "user", "content": ЗАДАНИЕ.replace("{firmy}", "\n".join(строки)).replace("{{", "{").replace("}}", "}")}],
                   "claude-sonnet-4-6", 2000, thinking=False, effort="low")
т = м if isinstance(м, str) else "".join(getattr(b, "text", "") for b in getattr(м, "content", []) or [])
try:
    _п = max(т.rfind('{"f"'), т.rfind('{ "f"'))
    _д = json.JSONDecoder(strict=False).raw_decode(т[_п:])[0]
    фразы = {int(x["n"]): x["t"] for x in (_д.get("f") or _д.get("firmy") or []) if len(str(x.get("t", "")).strip(" .")) > 15}
except Exception as _ex:  # noqa: BLE001
    фразы = {}
    print("ОТВЕТ МОДЕЛИ НЕ РАЗОБРАН:", _ex, repr(т[:600]))
if not фразы:
    print("ФРАЗ НЕТ, сырой ответ:", repr(т[:600]))
вых = []
for i, inn in enumerate(выбор, 1):
    fio, em, должн, тех = канд[inn]
    имя_комп = (e.execute("SELECT name FROM companies WHERE inn=?", (inn,)).fetchone() or [""])[0]
    _им = обращение(fio).split()[0].lower()
    mb = random.choice([m for m in ящики if str(getattr(m, "from_name", "") or "").split()[:1] != [_им.capitalize()]] or ящики)
    менеджер = (str(getattr(mb, "from_name", "") or "").split(",")[0].split() or ["Сергей"])[0]
    з = random.sample(ЗАК, 3)
    абз = [обращение(fio) + ", добрый день! Меня зовут " + менеджер + ", я из Компрессор Центра. " + random.choice(ПОВОД),
           (фразы.get(i, "") + " " if фразы.get(i) else "") + random.choice(ОХВАТ) + " " + random.choice(ЗАК_ФР).format(z=", ".join(з[:-1]) + " и " + з[-1], zt=", ".join(ЗАК_ТВ[x] for x in з[:-1]) + " и " + ЗАК_ТВ[з[-1]]) + " " + random.choice(СЕРВИС),
           random.choice(ВОПРОС) + ("" if тех else " " + random.choice(ПЕРЕСЛАТЬ))]
    вых.append("=== %d. %s | %s (%s) | %s | с ящика %s\n\n%s\n" % (i, имя_комп, fio, должн or "должность не указана", em, mb.mailbox_id, "\n\n".join(абз)))
т = "\n".join(вых)
print(т)
io.open(r"C:\sender\_ops\obrazcy-imennye-kc.txt", "w", encoding="utf-8").write(т)
