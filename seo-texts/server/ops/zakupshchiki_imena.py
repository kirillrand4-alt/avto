# -*- coding: utf-8 -*-
"""Владелец 06.11 «делай всё это»: закупщики (адреса снабжения/закупок из enrich.emails) —
можно ли обращаться по имени. Три слоя:
 1) механика: имя из словаря, без инициалов/отделов, порядок Имя-Фамилия, имя+отчество;
 2) связь с адресом: локальная часть адреса совпадает с фамилией/именем (транслит) — именной
    ящик; общий адрес — годится, если источник имени — сайт самой компании;
 3) спорные (флаг imya_ok не 1, а адрес именной) — модель пачкой: имя ли это и как обратиться.
Исключены: отвечали/жалоба/отписка, стоп-лист, мёртвый адрес, письмо на адрес < 15 дней,
уже в кампании «КЦ по имени 06.11». Направление — по базе обзвона (kc / meyer / оба).
Итог — счёт «по имени»/«без имени» по направлениям; решения — _ops/zakupshchiki-imena.jsonl (fsync).
    zakupshchiki_imena.py [--model]"""
import collections, io, json, os, re, sqlite3, sys, time
sys.path.insert(0, r"C:\sender"); sys.path.insert(0, r"C:\sender\server")
e = sqlite3.connect("file:C:\\sender\\enrich.db?mode=ro", uri=True, timeout=30)
s = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
o = sqlite3.connect("file:C:\\sender\\obzvon-index.db?mode=ro", uri=True, timeout=30)
ЗАК = re.compile(r"снабж|закуп|тендер|\bмтс\b|омтс|procure|purchas|zakup|snab|tender|omts", re.I)
ответ = {str(r[0]) for r in s.execute("SELECT DISTINCT r.inn FROM events e JOIN recipients r ON r.id=e.recipient_id WHERE e.event_type IN ('reply','complaint','unsubscribe')")}
стоп = {v.lower() for _, v in s.execute("SELECT scope, value FROM suppression")}
мёртв = {r[0].lower() for r in s.execute("SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX','неясно','отказ пробе')")}
адрес_15 = {r[0].lower() for r in s.execute("SELECT DISTINCT email FROM send_log WHERE outcome='sent' AND ts>=datetime('now','-15 days')")}
в_кампании = {str(r[0]) for r in s.execute("SELECT cr.inn FROM confirm_reviews cr JOIN campaigns c ON c.id=cr.campaign_id WHERE c.name='КЦ по имени 06.11'")}
напр = {}
for inn, d in o.execute("SELECT inn, division FROM obzvon"):
    d = str(d or "").lower(); к, м = "kc" in d, "meyer" in d
    напр[str(inn)] = "оба" if к and м else ("КЦ" if к else ("Meyer" if м else "?"))
сайт = {str(i): (str(x or "").lower().split("//")[-1].split("/")[0].replace("www.", "")) for i, x in e.execute("SELECT inn, site FROM companies WHERE site IS NOT NULL")}
ИМЕНА = set("""александр алексей анатолий андрей антон аркадий артём артем борис вадим валентин валерий василий виктор виталий владимир владислав вячеслав геннадий георгий глеб григорий даниил денис дмитрий евгений егор иван игорь илья кирилл константин леонид максим марат михаил никита николай олег павел пётр петр роман руслан рустам сергей станислав степан тимур фёдор федор эдуард юрий ярослав эльдар айдар ринат ильдар
александра алина алла анастасия анна антонина валентина валерия вера виктория галина дарья евгения екатерина елена жанна зинаида зоя инна ирина карина кристина лариса лидия любовь людмила маргарита марина мария надежда наталья наталия нина оксана ольга полина раиса светлана софья тамара татьяна ульяна юлия яна эльвира гульнара алёна алена милана""".split())
ТР = str.maketrans({"а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z","и":"i","й":"y","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f","х":"h","ц":"c","ч":"ch","ш":"sh","щ":"sch","ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya"})
def обращение(fio):
    ч = [x for x in re.split(r"\s+", (fio or "").strip()) if x]
    if not ч or any(len(x.strip(".")) <= 2 or "." in x for x in ч): return None
    if re.search(r"отдел|служб|снабж|закуп|менедж|специалист|бухгалт", fio, re.I): return None
    for i, x in enumerate(ч):
        if re.search(r"(вич|вна|ична|ьич)$", x, re.I) and i > 0 and ч[i - 1].lower() in ИМЕНА:
            return ч[i - 1] + " " + x
    for x in ч:
        if x.lower() in ИМЕНА: return x
    return None
def именной(em, fio):
    лок = re.sub(r"[^a-z]", "", em.split("@")[0].lower())
    for x in re.split(r"\s+", fio or ""):
        т = x.lower().translate(ТР)
        if len(т) >= 4 and (т[:5] in лок or (len(т) >= 5 and т[:4] in лок)): return True
    return False
ЖУР = io.open(r"C:\sender\_ops\zakupshchiki-imena.jsonl", "w", encoding="utf-8")
лучший = {}   # inn -> (ранг, решение) — одно письмо на компанию
сч = collections.Counter(); спорные = []
for inn, em, person, роль, src_url, imya_ok in e.execute("SELECT inn, email, person, COALESCE(role,'')||' '||COALESCE(zahod_rol,''), COALESCE(source_url,''), imya_ok FROM emails WHERE email IS NOT NULL"):
    inn, em = str(inn), (em or "").lower()
    if not (ЗАК.search(роль) or ЗАК.search(em.split("@")[0])): continue
    сч["адресов закупщиков"] += 1
    if inn in ответ: сч["искл: отвечали"] += 1; continue
    if em in стоп or inn in стоп: сч["искл: стоп-лист"] += 1; continue
    if em in мёртв: сч["искл: адрес мёртв"] += 1; continue
    if em in адрес_15: сч["искл: писали < 15 дней"] += 1; continue
    if inn in в_кампании: сч["искл: уже в «КЦ по имени»"] += 1; continue
    обр = обращение(person) if (person or "").strip() else None
    лич = именной(em, person) if обр else False
    свой_сайт = bool(src_url) and inn in сайт and сайт[inn] and сайт[inn] in src_url.lower()
    if not обр:
        реш = "без имени" + (" (имя негодно)" if (person or "").strip() else "")
    elif str(imya_ok) == "1" and (лич or свой_сайт or not src_url):
        реш = "по имени"
    elif лич:
        реш = "спорно: модель"; спорные.append((inn, em, person, обр))
    elif свой_сайт:
        реш = "по имени"
    else:
        реш = "без имени (имя не с сайта компании)"
    ранг = 0 if реш == "по имени" else (1 if реш.startswith("спорно") else 2)
    ЖУР.write(json.dumps({"inn": inn, "email": em, "person": person, "obr": обр, "lichnyy": лич, "svoy_sayt": свой_сайт, "imya_ok": imya_ok, "reshenie": реш, "napr": напр.get(inn, "?")}, ensure_ascii=False) + "\n")
    if inn not in лучший or ранг < лучший[inn][0]:
        лучший[inn] = (ранг, реш)
ЖУР.flush(); os.fsync(ЖУР.fileno())
if "--model" in sys.argv and спорные:
    import gen_provider as GP
    ЗАД = """Ниже ФИО из контактов компаний и предлагаемое обращение. Для каждого ответь: это имя живого человека
(не отдел, не компания, не мусор), и как правильно обратиться в деловом письме (имя и отчество, если отчество есть,
иначе имя). Если сомневаешься — ok=false.
{spisok}
Ответ - СТРОГО JSON вида {{"r": [{{"n": НОМЕР, "ok": true, "obr": "ОБРАЩЕНИЕ"}}]}}"""
    ок = 0
    for п0 in range(0, len(спорные), 150):
        пачка = спорные[п0:п0 + 150]
        стр = "\n".join("%d. %s | предложено: %s" % (i, x[2], x[3]) for i, x in enumerate(пачка, 1))
        for _п in range(6):
            try:
                м = GP._raw_stream([{"role": "user", "content": ЗАД.replace("{spisok}", стр).replace("{{", "{").replace("}}", "}")}], "claude-sonnet-4-6", 8000, thinking=False, effort="low")
                break
            except Exception as ex:  # noqa: BLE001
                if "429" not in str(ex): raise
                time.sleep(300)
        т = м if isinstance(м, str) else "".join(getattr(b, "text", "") for b in getattr(м, "content", []) or [])
        ii = max(т.rfind('{"r"'), т.rfind('{ "r"'))
        отв = {int(x["n"]): x for x in json.JSONDecoder(strict=False).raw_decode(т[ii:])[0].get("r", [])}
        with io.open(r"C:\sender\_ops\zakupshchiki-imena-model.jsonl", "a", encoding="utf-8") as ж:
            for i, x in enumerate(пачка, 1):
                р = отв.get(i, {})
                ж.write(json.dumps({"inn": x[0], "email": x[1], "person": x[2], "ok": bool(р.get("ok")), "obr": р.get("obr")}, ensure_ascii=False) + "\n")
                if р.get("ok"):
                    ок += 1
                    if лучший.get(x[0], (9,))[0] >= 1: лучший[x[0]] = (0, "по имени (модель)")
                elif лучший.get(x[0], (9, ""))[1].startswith("спорно"):
                    лучший[x[0]] = (2, "без имени (модель: не имя)")
            ж.flush(); os.fsync(ж.fileno())
    print("модель: спорных %d, годных %d" % (len(спорные), ок))
print("адреса:", dict(сч))
итог = collections.Counter((напр.get(inn, "?"), реш.split(" (")[0]) for inn, (_, реш) in лучший.items())
print("компаний: %d" % len(лучший))
for (н, р), v in sorted(итог.items()): print("   %-6s %-16s %d" % (н, р, v))
print("причины «без имени»:", collections.Counter(реш for _, реш in лучший.values() if реш.startswith("без")).most_common())
