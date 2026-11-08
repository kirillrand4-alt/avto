# -*- coding: utf-8 -*-
"""Владелец 08.11 «давай оба слоя запускай»: письма ЗАКУПЩИКАМ КЦ без имени («Добрый день!»), тот же заход и концовка, что у писем по имени. Адреса — из _ops/zakupshchiki-imena.jsonl (КЦ, без имени), только с пробой «есть»/«принимает всё». Основа — gen_imennye_kc.py: письма КЦ по имени (заход «бюджеты
на год», заказчики РУСАЛ/РЖД/Северсталь/Алроса) в «Подтвердить отправку», кампания
«КЦ по имени 06.11» (клон КЦ-1, id 17). Отправляет владелец сам.
Уникализация: варианты блоков + фраза про компанию от модели (пачка 20 = 1 вызов) +
перемешанные заказчики. Ящик закреплён за письмом (messages.mailbox_id): имя менеджера
в тексте = отправитель. Каждое 20-е письмо — в _ops/zakupshchiki-kc-kazhdoe20.txt (проверка глазами).
Журнал _ops/zakupshchiki-kc.jsonl (fsync); резюм — по карточкам кампании в базе.
    gen_imennye_kc.py [--zapusk] [--limit=N]"""
import io, json, os, random, re, sqlite3, subprocess, sys, time
from datetime import datetime, timezone
if "--zapusk" in sys.argv:
    лог = io.open(r"C:\sender\_ops\zakupshchiki-kc.log", "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__), "--rabota"] + [a for a in sys.argv[1:] if a.startswith("--limit=") or a.startswith("--fayl=") or a == "--panel"],
                         cwd=r"C:\sender", stdout=лог, stderr=лог, creationflags=0x00000008 | 0x00000200)
    time.sleep(8); print("запущен, pid %d, жив %s" % (п.pid, п.poll() is None)); sys.exit(0)
sys.path.insert(0, r"C:\sender"); sys.path.insert(0, r"C:\sender\server")
from sender.config import Config   # noqa: E402
from sender.store import Store     # noqa: E402
from sender.ai_quota import build_ai_quota  # noqa: E402
import gen_provider as GP          # noqa: E402
_сырой = GP._raw_stream
def _с_ожиданием(*a, **k):
    for _п in range(8):
        try:
            return _сырой(*a, **k)
        except Exception as ex:  # noqa: BLE001
            if "429" not in str(ex) or _п == 7:
                raise
            print("шлюз 429, жду 5 мин", flush=True); time.sleep(300)
GP._raw_stream = _с_ожиданием
ЛИМИТ = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--limit=")), 100000)
ИМЯ_КАМП = "КЦ закупщики 08.11"
random.seed()
s = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
e = sqlite3.connect("file:C:\\sender\\enrich.db?mode=ro", uri=True, timeout=30)
o = sqlite3.connect("file:C:\\sender\\obzvon-index.db?mode=ro", uri=True, timeout=30)
кц = {str(i) for i, d in o.execute("SELECT inn, division FROM obzvon") if "kc" in str(d or "").lower()}
недавно = {str(r[0]) for r in s.execute("SELECT DISTINCT inn FROM send_log WHERE outcome='sent' AND ts>=datetime('now','-15 days') AND inn IS NOT NULL")}  # владелец 06.11: 15 дней
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
# Источники (владелец 06.11): enrich.emails с подтверждённым именем; --panel — получатели панели
# с contact_name (база КЦ-1, Россия 9000, spaseno182), должность из extra.stupen.
ФАЙЛ = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--fayl=")), None)
def _из_файла(имя):
    """Лист «Контакты с сайта» / «Контакты» xlsx с дропа (FSA-MEYER-v4-KC и т.п.): ИНН, ФИО, должность, роль, e-mail."""
    import requests, openpyxl
    for line in io.open(r"C:\sender\panel.env", encoding="utf-8", errors="replace").read().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k_, v_ = line.split("=", 1); os.environ.setdefault(k_.strip(), v_.strip().strip('"'))
    п = os.path.join(r"C:\sender\_ops", имя)
    if not os.path.exists(п):
        р = requests.get(os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/") + "/" + имя, headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=300)
        р.raise_for_status(); io.open(п, "wb").write(р.content)
    wb = openpyxl.load_workbook(п, read_only=True)
    ws = wb["Контакты с сайта"] if "Контакты с сайта" in wb.sheetnames else wb["Контакты"]
    rows = ws.iter_rows(values_only=True); h = list(next(rows))
    ix = {k: h.index(k) for k in ("ИНН / УНП", "ФИО", "Должность (как на сайте)", "Роль", "E-mail")}
    for r in rows:
        em = str(r[ix["E-mail"]] or "").strip()
        fio = str(r[ix["ФИО"]] or "").strip()
        if em and fio and "@" in em:
            yield str(r[ix["ИНН / УНП"]] or ""), fio, str(r[ix["Должность (как на сайте)"]] or ""), str(r[ix["Роль"]] or ""), em
ИЗ_ФАЙЛА = {}   # inn -> (название, продукция кратко) из листа «Работа» FSA-файла
def _работа(имя):
    import openpyxl
    п = os.path.join(r"C:\sender\_ops", имя)
    if not os.path.exists(п): return
    wb = openpyxl.load_workbook(п, read_only=True)
    if "Работа" not in wb.sheetnames: return
    rows = wb["Работа"].iter_rows(values_only=True); h = list(next(rows))
    if "ИНН" not in h: return
    iИ, iК = h.index("ИНН"), (h.index("Компания") if "Компания" in h else h.index("Название"))
    iП = h.index("Продукция (кратко)") if "Продукция (кратко)" in h else None
    for r in rows:
        ИЗ_ФАЙЛА[str(r[iИ] or "")] = (str(r[iК] or ""), str(r[iП] or "") if iП is not None else "")
def _источник():
    if ФАЙЛ:
        yield from _из_файла(ФАЙЛ)
        _работа(ФАЙЛ)
        return
    if "--panel" in sys.argv:
        for inn, person, em, seg, ex in s.execute("SELECT inn, contact_name, email, segment, extra_json FROM recipients WHERE inn IS NOT NULL AND contact_name IS NOT NULL AND trim(contact_name)!='' AND email IS NOT NULL"):
            x = json.loads(ex or "{}")
            if not (str(seg or "") == "кц" or x.get("target_division") == "kc" or "kc" in str(x.get("divisions") or "")):
                continue
            yield inn, person, str(x.get("stupen") or x.get("dolzhnost") or ""), "", em
    else:
        yield from e.execute("SELECT inn, person, COALESCE(zahod_rol,''), COALESCE(role,''), email FROM emails WHERE person IS NOT NULL AND trim(person)!='' AND imya_ok='1' AND email IS NOT NULL")
ПРОБА_ЖИВ = {r_[0].lower() for r_ in s.execute("SELECT email FROM addr_probe WHERE verdict IN ('есть','принимает всё')")}
в_именах = {str(r_[0]) for r_ in s.execute("SELECT cr.inn FROM confirm_reviews cr JOIN campaigns c ON c.id=cr.campaign_id WHERE c.name='КЦ по имени 06.11' AND cr.status!='skipped'")}
def _источник():
    for _с in io.open(r"C:\sender\_ops\zakupshchiki-imena.jsonl", encoding="utf-8"):
        _з = json.loads(_с)
        if _з.get("napr") == "КЦ" and _з["reshenie"].startswith("без") and _з["email"] in ПРОБА_ЖИВ and _з["inn"] not in в_именах:
            yield _з["inn"], "", "снабжение", "снабжение", _з["email"]
for inn, person, post, role, em in _источник():
    inn, em = str(inn), em.lower()
    if not re.search(r"\.(ru|рф|su|com|org|net|pro|biz|info)$", em) or em.endswith(".by"):
        continue
    if not (отрасль_годна(inn) or (ФАЙЛ and not e.execute("SELECT 1 FROM companies WHERE inn=? AND okved IS NOT NULL AND okved!=''", (inn,)).fetchone())) or inn in ответ or inn in недавно or em in стоп or inn in стоп or em in мёртв:
        continue
    тех = bool(re.search(ТЕХ, post + " " + role, re.I))
    if inn not in канд:
        канд[inn] = (person.strip(), em, (post or role).strip(), тех)
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

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
к = store._conn
# ---- кампания-клон КЦ-1
r = к.execute("SELECT id FROM campaigns WHERE name=?", (ИМЯ_КАМП,)).fetchone()
if r:
    КАМП = r[0]
elif "--rabota" not in sys.argv:
    КАМП = -1
else:
    б = к.execute("SELECT status, legal_entity, legal_inn, provider_pool, config_json FROM campaigns WHERE id=17").fetchone()
    сейчас = datetime.now(timezone.utc).isoformat()
    with store._lock:
        КАМП = к.execute("INSERT INTO campaigns (name, status, legal_entity, legal_inn, provider_pool, config_json, created_at, updated_at) "
                         "VALUES (?,?,?,?,?,?,?,?)", (ИМЯ_КАМП, б[0], б[1], б[2], б[3], б[4], сейчас, сейчас)).lastrowid
        шк = [x[1] for x in к.execute("PRAGMA table_info(sequence_steps)") if x[1] != "id"]
        for row in к.execute("SELECT %s FROM sequence_steps WHERE campaign_id=17" % ",".join(шк)).fetchall():
            д = dict(zip(шк, row)); д["campaign_id"] = КАМП
            к.execute("INSERT INTO sequence_steps (%s) VALUES (%s)" % (",".join(д), ",".join("?" * len(д))), list(д.values()))
        к.commit()
    print("заведена кампания", КАМП, ИМЯ_КАМП, flush=True)
q = build_ai_quota(store, cfg) if "--rabota" in sys.argv else None
# ---- кандидаты: доп. исключения — карточка уже есть в этой кампании, письмо в очереди, тот же адрес < 30 дней
готовы = {str(x[0]) for x in к.execute("SELECT inn FROM confirm_reviews WHERE campaign_id=? AND NOT (status='skipped' AND reason LIKE 'общая фраза%')", (КАМП,))}
в_очереди = {str(x[0]) for x in к.execute("SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status IN ('scheduled','sending','pending_review')")}
адрес_30 = {x[0].lower() for x in к.execute("SELECT DISTINCT email FROM send_log WHERE outcome='sent' AND ts>=datetime('now','-15 days')")}  # владелец 06.11: 15 дней
список = [i for i in sorted(канд) if i not in готовы and i not in в_очереди and канд[i][1] not in адрес_30]
random.shuffle(список)
список = список[:ЛИМИТ]
print("кандидатов: %d (уже в кампании %d), берём %d" % (len(канд), len(готовы), len(список)), flush=True)
if "--rabota" not in sys.argv:
    print("сухой прогон: генерации нет. Запуск — --zapusk"); sys.exit(0)
ЖУР = io.open(r"C:\sender\_ops\zakupshchiki-kc.jsonl", "a", encoding="utf-8")
ГЛАЗ = io.open(r"C:\sender\_ops\zakupshchiki-kc-kazhdoe20.txt", "a", encoding="utf-8")
def фраза_годна(т):
    т = (т or "").strip()
    if len(т) < 25 or len(т.split()) > 30: return False
    if re.search(r"\d|—|\bмы\b|\bнаш|компрессор центр", т, re.I): return False
    if re.search(r"^На производстве сжатый воздух|технологических (процесс|нужд)|может применяться|^На производственном участке|специализированн\w* строительн|вспомогательн\w* (технологическ|оборудован)", т, re.I): return False
    return "сжат" in т.lower()
заведено = 0
for п0 in range(0, len(список), 20):
    пачка = список[п0:п0 + 20]
    строки = []
    for i, inn in enumerate(пачка, 1):
        r = e.execute("SELECT name, okved, substr(COALESCE(activity,''),1,300) FROM companies WHERE inn=?", (inn,)).fetchone() or ("", "", "")
        if not (r[0] and (r[1] or r[2])) and inn in ИЗ_ФАЙЛА:
            r = (ИЗ_ФАЙЛА[inn][0], r[1] or "", ИЗ_ФАЙЛА[inn][1][:300])
        строки.append("%d. %s; ОКВЭД %s; %s" % (i, r[0], r[1], r[2]))
    try:
        м = GP._raw_stream([{"role": "user", "content": ЗАДАНИЕ.replace("{firmy}", "\n".join(строки)).replace("{{", "{").replace("}}", "}")}],
                           "claude-sonnet-4-6", 3000, thinking=False, effort="low")
        т = м if isinstance(м, str) else "".join(getattr(b, "text", "") for b in getattr(м, "content", []) or [])
        _п = max(т.rfind('{"f"'), т.rfind('{ "f"'))
        фразы = {int(x["n"]): x["t"] for x in json.JSONDecoder(strict=False).raw_decode(т[_п:])[0].get("f", [])}
    except Exception as ex:  # noqa: BLE001
        print("пачка %d: модель не дала фраз: %s" % (п0, str(ex)[:150]), flush=True)
        continue
    for i, inn in enumerate(пачка, 1):
        fio, em, должн, тех = канд[inn]
        ф = фразы.get(i, "")
        запись = {"inn": inn, "email": em, "fio": fio, "post": должн, "ts": datetime.now(timezone.utc).isoformat()}
        if not фраза_годна(ф):
            запись["otsev"] = "фраза модели: %r" % ф[:120]
            ЖУР.write(json.dumps(запись, ensure_ascii=False) + "\n"); ЖУР.flush(); os.fsync(ЖУР.fileno())
            continue
        имя_комп = (e.execute("SELECT name FROM companies WHERE inn=?", (inn,)).fetchone() or [""])[0] or ИЗ_ФАЙЛА.get(inn, ("", ""))[0]
        mb = random.choice(ящики)
        менеджер = (str(getattr(mb, "from_name", "") or "").split(",")[0].split() or ["Сергей"])[0]
        з = random.sample(ЗАК, 3)
        абз = ["Добрый день! Меня зовут " + менеджер + ", я из Компрессор Центра. " + random.choice(ПОВОД),
               ф.strip() + " " + random.choice(ОХВАТ) + " " + random.choice(ЗАК_ФР).format(z=", ".join(з[:-1]) + " и " + з[-1], zt=", ".join(ЗАК_ТВ[x] for x in з[:-1]) + " и " + ЗАК_ТВ[з[-1]]) + " " + random.choice(СЕРВИС),
               random.choice(ВОПРОС) + " " + random.choice(ПЕРЕСЛАТЬ)]
        тело = "\n\n".join(абз)
        тема = random.choice(["Вопрос по компрессорной на следующий год", "Компрессорная: планы на следующий год", "Вопрос по сжатому воздуху на производстве"])
        # получатель
        есть = к.execute("SELECT id, inn FROM recipients WHERE lower(email)=?", (em,)).fetchone()
        if есть and есть[1] and str(есть[1]) != inn:
            запись["otsev"] = "адрес закреплён за другим ИНН %s" % есть[1]
            ЖУР.write(json.dumps(запись, ensure_ascii=False) + "\n"); ЖУР.flush(); os.fsync(ЖУР.fileno()); continue
        сейчас = datetime.now(timezone.utc).isoformat()
        if есть:
            rid = есть[0]
        else:
            with store._lock:
                rid = к.execute("INSERT INTO recipients (email, company_name, inn, segment, domain, tz, contact_name, source, extra_json, created_at, updated_at) "
                                "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (em, имя_комп, inn, "кц", em.split("@")[-1], "Europe/Moscow", fio,
                                "zakupshchiki-kc-0811", json.dumps({"target_division": "kc", "stupen": должн}, ensure_ascii=False), сейчас, сейчас)).lastrowid
                к.commit()
        mid, _шаг, почему = q._ensure_message(КАМП, int(rid))
        if not mid:
            запись["otsev"] = "сообщение не завелось: %s" % почему
            ЖУР.write(json.dumps(запись, ensure_ascii=False) + "\n"); ЖУР.flush(); os.fsync(ЖУР.fileno()); continue
        панель = json.dumps({"letter_division": "kc", "mailbox_id": mb.mailbox_id, "vruchnuyu": "КЦ закупщики 08.11", "company": {"name": имя_комп}}, ensure_ascii=False)
        with store._lock:
            к.execute("UPDATE messages SET mailbox_id=? WHERE id=?", (mb.mailbox_id, mid))
            к.execute("UPDATE messages SET status='pending_review', last_error=NULL WHERE id=? AND status='skipped' AND last_error='общая фраза'", (mid,))
            _ст = к.execute("SELECT id FROM confirm_reviews WHERE dedup_key=? AND status='skipped' AND reason LIKE 'общая фраза%'", ("%s|%s|%d" % (inn, em, КАМП),)).fetchone()
        if _ст:
            with store._lock:
                к.execute("UPDATE confirm_reviews SET subject=?, body=?, panel_json=?, status='pending', reason=NULL, decided_at=NULL, message_id=?, updated_at=? WHERE id=?",
                          (тема, тело, панель, mid, сейчас, _ст[0]))
                к.commit()
            кид = _ст[0]
        else:
          with store._lock:
            кид = к.execute("INSERT INTO confirm_reviews (dedup_key, campaign_id, recipient_id, message_id, inn, email, subject, body, panel_json, status, kind, created_at, updated_at) "
                            "VALUES (?,?,?,?,?,?,?,?,?,'pending','outbound',?,?)", ("%s|%s|%d" % (inn, em, КАМП), КАМП, rid, mid, inn, em, тема, тело, панель, сейчас, сейчас)).lastrowid
            к.commit()
        заведено += 1
        запись.update({"karta": кид, "mailbox": mb.mailbox_id, "tema": тема, "telo": тело})
        ЖУР.write(json.dumps(запись, ensure_ascii=False) + "\n"); ЖУР.flush(); os.fsync(ЖУР.fileno())
        if i == 1:
            ГЛАЗ.write("=== #%d %s | %s (%s) | %s | %s\nТема: %s\n\n%s\n\n" % (кид, имя_комп, fio, должн, em, mb.mailbox_id, тема, тело)); ГЛАЗ.flush()
    print("пачка %d: заведено всего %d" % (п0 // 20 + 1, заведено), flush=True)
print("итог: заведено %d" % заведено, flush=True)
