# -*- coding: utf-8 -*-
"""Лёгкая проверка всей базы: у каких доменов вообще нет почтового сервера.

Владелец 13.08: «мы можем те адреса, где лёгкая проверка и они её провалили,
убрать сразу из базы?». Лёгкая — та, что решается без разговора с чужим
почтовым сервером: формат адреса и наличие MX у домена. Репутацию не тратит,
работника на VPS не занимает, и главное — проверяет ДОМЕНЫ: на одном домене
сидят десятки контактов, один запрос закрывает всех.

Два прохода, и это важно:
  1) быстрый — dnspython спрашивает MX у всех доменов в несколько потоков;
  2) придирчивый — только к тем, у кого MX не нашлось: перепроверяем системным
     резолвером и A-записью, и хороним домен ТОЛЬКО при полном согласии.

Почему так. Одного пустого ответа мало: резолвер сбоит, ответ срезается, а
выброшенный домен назад не вернёшь — за ним могут стоять сто живых контактов.
Второй проход дорогой, но он достаётся меньшинству.

ПРИМЕНЯЕМ СРАЗУ, в той же партии. Владелец 13.08: «ты их выкидываешь сразу?
а то мы это уже проверяли, но ничего не сделали с этим» — и это правда: прогон
по доменам-подменам нашёл 76 мёртвых и закончился строкой «снято писем: 0,
адресов в стоп-лист: 0». Проверка без применения бесполезна, поэтому здесь
вердикт кладётся в базы тем же проходом, а в прогрессе отмечается «primeneno».

Не удаляем, а помечаем. Строку контакта стирать нельзя: пропадёт след, откуда
он взялся, а домен может ожить — пометку пересчитать можно, удаление
необратимо.

Прогресс durable: рестарт контейнера не теряет проверенное.
"""
import json
import os
import re
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r"C:\sender")

ПРОГРЕСС = r"C:\sender\_ops\lyogkaya-progress.json"
ИТОГ = r"C:\sender\_ops\lyogkaya-itog.json"
ПОТОКОВ = 16
ЗА_РАЗ = int(sys.argv[1]) if len(sys.argv) > 1 else 3000

ФОРМАТ = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Zа-яА-ЯёЁ]{2,}$")

# --- собрать адреса и домены -------------------------------------------------- #
РАЗБИТЬ = re.compile(r"[;,\s|]+")
адреса = set()
for путь, запрос in ((r"C:\sender\enrich.db", "SELECT email FROM emails"),
                     (r"C:\sender\sender.db", "SELECT email FROM recipients")):
    c = sqlite3.connect(f"file:{путь}?mode=ro", uri=True, timeout=30)
    for (а,) in c.execute(запрос):
        а = str(а or "").strip().lower()
        if а:
            адреса.add(а)
    c.close()
# База обзвона на 161к: её почты лежат двумя колонками через разделители, и в
# прошлый замер они не попали вовсе (владелец: «8к доменов на 161к базу?»).
o = sqlite3.connect(r"file:C:\sender\obzvon-index.db?mode=ro", uri=True,
                    timeout=180)
for eb, es in o.execute("SELECT emails_base, emails_site FROM obzvon"):
    for сырое in (eb, es):
        for а in РАЗБИТЬ.split(str(сырое or "")):
            а = а.strip().lower().strip('"<>()')
            if а and "@" in а:
                адреса.add(а)
o.close()

# Публичные почтовики лёгкой проверкой не проверяются: MX у них есть заведомо,
# а мёртвый ящик там ловит только SMTP-проба. Считать их незачем — это две
# трети базы, и они только раздували бы очередь DNS-запросов.
ПУБЛИЧНЫЕ = {
    "mail.ru", "yandex.ru", "ya.ru", "gmail.com", "bk.ru", "list.ru",
    "inbox.ru", "rambler.ru", "internet.ru", "icloud.com", "mail.com",
    "gmail.ru", "outlook.com", "hotmail.com", "yahoo.com", "yandex.com",
    "narod.ru", "vk.com", "me.com", "protonmail.com", "bk.com",
}

кривые = sorted(а for а in адреса if not ФОРМАТ.match(а))
домены = {}
for а in адреса:
    if "@" in а and ФОРМАТ.match(а):
        д = а.rsplit("@", 1)[-1]
        if д not in ПУБЛИЧНЫЕ:
            домены.setdefault(д, []).append(а)

готово = {}
if os.path.exists(ПРОГРЕСС):
    with open(ПРОГРЕСС, encoding="utf-8") as f:
        готово = json.load(f)
осталось = [д for д in домены if д not in готово]
print(f"адресов {len(адреса)}, доменов {len(домены)}, кривой формат {len(кривые)}")
print(f"проверено ранее {len(готово)}, осталось {len(осталось)}")

# --- проход 1: быстрый вопрос про MX ------------------------------------------ #
_замок = threading.Lock()


def _mx_быстро(домен):
    try:
        import dns.resolver
        о = dns.resolver.resolve(домен, "MX", lifetime=8)
        сп = [str(r.exchange).rstrip(".") for r in о]
        return ("есть", сп[0] if сп else "")
    except Exception as e:  # noqa: BLE001
        т = repr(e)
        if "NXDOMAIN" in т:
            return ("домена нет", "")
        if "NoAnswer" in т or "NoRecords" in т:
            return ("пусто", "")
        return ("молчит", т[:60])


партия = осталось[:ЗА_РАЗ]
быстро = {}
if партия:
    with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
        for д, р in zip(партия, пул.map(_mx_быстро, партия)):
            быстро[д] = р
    сч = {}
    for в, _ in быстро.values():
        сч[в] = сч.get(в, 0) + 1
    print(f"\nбыстрый проход по {len(партия)}: {сч}")

# --- проход 2: придирчиво к подозрительным ------------------------------------ #
подозрительные = [д for д, (в, _) in быстро.items()
                  if в in ("пусто", "домена нет")]
print(f"под подозрением (MX не найден): {len(подозрительные)}")

приговор = {}
if подозрительные:
    from sender.addr_probe import AddrProbe
    проба = AddrProbe.__new__(AddrProbe)

    def _придирчиво(д):
        try:
            мёртв, почему = проба._net_mx_dvazhdy(д)
        except Exception as e:  # noqa: BLE001
            return (False, f"сбой: {str(e)[:50]}")
        return (bool(мёртв), почему[:90])

    with ThreadPoolExecutor(max_workers=8) as пул:
        for д, р in zip(подозрительные, пул.map(_придирчиво, подозрительные)):
            приговор[д] = р

for д in партия:
    в, деталь = быстро.get(д, ("молчит", ""))
    if д in приговор:
        мёртв, почему = приговор[д]
        готово[д] = {"mertv": bool(мёртв), "pochemu": почему,
                     "adresov": len(домены[д])}
    else:
        готово[д] = {"mertv": False, "pochemu": f"{в}: {деталь}"[:90],
                     "adresov": len(домены[д])}

with open(ПРОГРЕСС, "w", encoding="utf-8") as f:
    json.dump(готово, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())

мёртвые = sorted(д for д, з in готово.items() if з["mertv"])
адресов_мёртвых = sum(готово[д]["adresov"] for д in мёртвые)
print(f"\nПРОВЕРЕНО ВСЕГО {len(готово)} доменов из {len(домены)}")
print(f"МЁРТВЫХ ДОМЕНОВ: {len(мёртвые)}, за ними адресов: {адресов_мёртвых}")
print("самые крупные мёртвые:")
for д in sorted(мёртвые, key=lambda x: -готово[x]["adresov"])[:12]:
    print(f"   {д:<38} {готово[д]['adresov']:>4} адресов | "
          f"{готово[д]['pochemu'][:44]}")

# --- ПРИМЕНЕНИЕ: вердикт в базы, письма с очереди ------------------------------ #
к_применению = [д for д in мёртвые if not готово[д].get("primeneno")]
if к_применению:
    адреса_мёртвых = []
    for д in к_применению:
        адреса_мёртвых.extend(домены.get(д, []))
    print(f"\nПРИМЕНЯЮ: доменов {len(к_применению)}, адресов "
          f"{len(адреса_мёртвых)}")

    # 1) кэш пробы панели — его читают заслон подтверждения и фильтр списка
    #    «кому», поэтому адрес пропадает из работы сразу.
    from datetime import datetime, timezone
    сейчас = datetime.now(timezone.utc).isoformat()
    c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
    c.executemany(
        "INSERT INTO addr_probe (email,verdict,code,answer,mx,ts) "
        "VALUES (?,?,?,?,?,?) ON CONFLICT(email) DO UPDATE SET "
        "verdict=excluded.verdict, answer=excluded.answer, ts=excluded.ts",
        [(а, "нет MX", None, "у домена нет почтового сервера (лёгкая проверка)",
          "", сейчас) for а in адреса_мёртвых])
    c.commit()

    # 2) письма этих адресов снимаем с очереди подтверждения
    снято = 0
    метки = ",".join("?" * min(500, len(адреса_мёртвых)))
    for i in range(0, len(адреса_мёртвых), 500):
        кусок = адреса_мёртвых[i:i + 500]
        ids = [r[0] for r in c.execute(
            "SELECT id FROM confirm_reviews WHERE status='pending' "
            "AND LOWER(email) IN (%s)" % ",".join("?" * len(кусок)), кусок)]
        for пид in ids:
            c.execute(
                "UPDATE confirm_reviews SET status='skipped', "
                "reason=?, decided_by=?, updated_at=? WHERE id=? "
                "AND status='pending'",
                ("у домена нет почтового сервера (лёгкая проверка базы)",
                 "лёгкая проверка доменов", сейчас, пид))
            снято += 1
    c.commit()
    c.close()
    print(f"  снято писем с очереди: {снято}")

    # 3) база обогащения — её читает отбор кандидатов
    try:
        from sender.probe_enrich import записать
        итог_об = записать(r"C:\sender\enrich.db",
                           [{"email": а, "verdict": "нет MX",
                             "answer": "нет почтового сервера у домена"}
                            for а in адреса_мёртвых])
        print(f"  в обогащении помечено: {итог_об}")
    except Exception as e:  # noqa: BLE001
        print(f"  обогащение не обновилось: {str(e)[:90]}")

    for д in к_применению:
        готово[д]["primeneno"] = True
    with open(ПРОГРЕСС, "w", encoding="utf-8") as f:
        json.dump(готово, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())

if len(готово) >= len(домены):
    with open(ИТОГ, "w", encoding="utf-8") as f:
        json.dump({"mertvye_domeny": мёртвые,
                   "adresov_za_nimi": адресов_мёртвых,
                   "krivoy_format": кривые,
                   "vsego_domenov": len(домены),
                   "vsego_adresov": len(адреса)}, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    print("\nВСЕ ПРОВЕРЕНЫ. Итог:", ИТОГ)
else:
    print(f"\nосталось {len(домены) - len(готово)} — запусти ещё раз")
