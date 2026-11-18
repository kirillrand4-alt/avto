# -*- coding: utf-8 -*-
"""Фраза «что мы для вас делали» по сделкам клиента СЦ (владелец 18.11: «можем написать что-то типа мейеровских писем?»).
Источник — дроп kc_sc_sdelki_all.csv (все сделки КЦ и СЦ: DEAL_ID;TITLE;…;ВОРОНКА;…;СТАТУС;…;CLOSEDATE;…;INN). Берутся
успешные сделки компании (любая воронка), модель по их НАЗВАНИЯМ пишет одну фразу о прошлой работе; если названия
пустые (только компания и дата) — запасная строка «вы обращались в наш сервисный центр» с годом.
Модуль: sdelki(инн) -> список сделок; frazy([(ключ, инн)]) -> {ключ: {"f", "god", "ist"}}.
Запуск сам по себе: kc_sc_sdelki_fraza.py --obrazcy [N=12] — образцы писем (карточек не заводит)."""
import csv, io, json, os, random, re, sys, time
from collections import defaultdict
csv.field_size_limit(10 ** 9)
ц = lambda x: "".join(c for c in str(x or "") if c.isdigit())
СД = defaultdict(list)
for р in csv.DictReader(io.open(r"C:\seostat\drop\drop-storage\kc_sc_sdelki_all.csv", encoding="utf-8-sig", errors="replace"), delimiter=";"):
    if р.get("СТАТУС") == "Успешна" and ц(р.get("INN")):
        СД[ц(р["INN"])].append({"t": (р.get("TITLE") or "").strip(), "v": р.get("ВОРОНКА") or "", "d": (р.get("CLOSEDATE") or р.get("DATE_CREATE") or "")[:10]})


def sdelki(инн):
    return sorted(СД.get(ц(инн), []), key=lambda x: x["d"], reverse=True)


СИСТЕМА = """Ты пишешь ОДНУ фразу для письма менеджера Компрессор Центра (компрессоры, осушители, фильтры, сервисный центр)
бывшему клиенту. Даны его УСПЕШНЫЕ сделки с нами: дата закрытия | воронка | название сделки.
Фраза говорит, что мы для него делали, по самым содержательным сделкам: поставка компрессора, осушителя, фильтров,
расходников, масла, запчастей, ремкомплектов; ТО, ремонт, пусконаладка (ПНР), выезд инженера, гарантийный ремонт.
Начни с года той сделки, о которой говоришь: «В 2024 году наш сервисный центр проводил ТО вашего компрессора Dalgakiran»,
«В 2023 году мы поставляли вам фильтры и масло для компрессора», «В 2025 году наш инженер выезжал к вам на пусконаладку».
ТОЛЬКО то, что видно в названиях. Марку/модель — только если она написана в названии. Не упоминай номера заказов, суммы,
имена людей, города, слова «перекуп», «дубль», «заказ покупателя», названия компаний. Без длинного тире, без восклицаний,
без оценок. До 22 слов. Если названия ничего не говорят о работе (только название компании и дата) — "f" пустая.
"god" — год последней успешной сделки (из дат).
Ответ СТРОГО JSON: {"k": [{"n": НОМЕР, "f": "...", "god": "2024"}]}"""
ЗАПАС = ["В {god} году вы обращались в наш сервисный центр, так что мы с вами уже работали.",
         "Мы с вами уже работали: в {god} году ваша компания обращалась в наш сервисный центр.",
         "В {god} году ваша компания работала с нашим сервисным центром."]


def _годна(ф, сд):
    if not ф or len(ф.split()) > 28 or "—" in ф or "!" in ф: return False
    if re.search(r"(?i)перекуп|дубл|заказ покупателя|\d{5,}|руб", ф): return False
    for м in re.findall(r"\b[A-Z][A-Za-z\-]{2,}\b", ф):        # марка в латинице — должна быть в названиях
        if м.lower() not in " ".join(x["t"].lower() for x in сд): return False
    return True


def frazy(пары, зов, макс_пачка=10):
    """пары: [(ключ, инн)]; зов(текст, ключ_json, система, макс) -> dict|None. Возврат {ключ: {f, god, ist}}."""
    вых = {}
    for п0 in range(0, len(пары), макс_пачка):
        пачка = пары[п0:п0 + макс_пачка]
        блоки = []
        for i, (кл, инн) in enumerate(пачка, 1):
            сд = sdelki(инн)[:8]
            блоки.append("%d.\n%s" % (i, "\n".join("   %s | %s | %s" % (x["d"], x["v"], x["t"][:160]) for x in сд) or "   (сделок нет)"))
        д = зов("\n\n".join(блоки), "k", СИСТЕМА, 2500) or {}
        отв = {int(x.get("n", 0)): x for x in д.get("k") or [] if str(x.get("n", "")).isdigit()}
        for i, (кл, инн) in enumerate(пачка, 1):
            сд = sdelki(инн)
            год = (отв.get(i, {}).get("god") or (сд[0]["d"][:4] if сд else "")).strip()[:4]
            ф = (отв.get(i, {}).get("f") or "").strip().replace("—", "-")
            if _годна(ф, сд):
                вых[кл] = {"f": ф, "god": год, "ist": "сделки"}
            elif год.isdigit():
                вых[кл] = {"f": random.choice(ЗАПАС).format(god=год), "god": год, "ist": "запас"}
            else:
                вых[кл] = {"f": "Мы с вами уже работали: ваша компания обращалась в наш сервисный центр.", "god": "", "ist": "запас без года"}
    return вых


if __name__ == "__main__" and "--obrazcy" in sys.argv:
    sys.path.insert(0, r"C:\sender"); sys.path.insert(0, r"C:\sender\server"); sys.path.insert(0, r"C:\sender\server\ops")
    os.environ["PROVIDER_THINKING_FIELD"] = "omit"
    import gen_provider as GP
    import gen_9000_kc_kanon as KK

    def зов(текст, ключ, система, макс):
        for п in range(8):
            try:
                м = GP._raw_stream([{"role": "user", "content": текст}], "claude-opus-4-8", макс, thinking=False, effort=None, system=система, cache_system=True)
                т = м if isinstance(м, str) else "".join(getattr(b, "text", "") or "" for b in getattr(м, "content", []) or [])
                мм = list(re.finditer(r'\{\s*"%s"\s*:' % ключ, т))
                if not мм: raise ValueError("нет JSON")
                return json.JSONDecoder(strict=False).raw_decode(т[мм[-1].start():])[0]
            except Exception as ex:  # noqa: BLE001
                print("модель: %s" % str(ex)[:100], flush=True); time.sleep(20)
        return None
    N = int(next((a for a in sys.argv[1:] if a.isdigit()), "12"))
    лес = {}
    for с in io.open(r"C:\sender\_ops\kc-sc-lesenka.jsonl", encoding="utf-8"):
        x = json.loads(с)
        if x.get("status") == "выбран": лес[x["kluch"]] = x
    кл = [k for k in лес if not k.startswith("имя:")]; random.seed(1811); random.shuffle(кл); кл = кл[:N]
    фр = frazy([(k, k) for k in кл], зов)
    for k in кл:
        л_ = лес[k]; обр = л_.get("imya") or ""
        з = random.sample(KK.ЗАК, 3)
        тело = "\n\n".join([((обр + ", добрый день!") if обр else "Добрый день!") + " Меня зовут Вячеслав, я из Компрессор Центра. " + random.choice(KK.ПОВОД),
                            фр[k]["f"] + " " + random.choice(KK.ОХВАТ) + " " + random.choice(KK.ЗАК_ФР).format(z=", ".join(з[:-1]) + " и " + з[-1], zt=", ".join(KK.ЗАК_ТВ[x] for x in з[:-1]) + " и " + KK.ЗАК_ТВ[з[-1]]),
                            random.choice(KK.ВОПРОС) + ("" if л_.get("teh") else " " + random.choice(KK.ПЕРЕСЛАТЬ))])
        print("=== %s | %s | фраза: %s\n   сделки: %s\n\n%s\n" % (k, л_.get("email"), фр[k]["ist"], " / ".join("%s %s" % (x["d"][:4], x["t"][:70]) for x in sdelki(k)[:4]), тело))
