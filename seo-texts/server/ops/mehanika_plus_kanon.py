# -*- coding: utf-8 -*-
"""Механическое письмо + один прогон канона редактора: что выходит и почём.

Владелец: «то есть за 0.05 будут нормальные письма?». Обещать нельзя,
можно показать. Механика даёт факты и структуру, один дешёвый вызов
переписывает формулировки — уникальным становится всё письмо, а не один
абзац из шести.

Заход РОТИРУЕТСЯ по кругу: без этого модель перепишет одинаково, и
монотонность вернётся тем же путём, каким пришла.
"""
import io
import json
import re
import sys
import time

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

import gen_provider                                            # noqa: E402
from sender.ai_letter import (gate, load_facts, короткое_имя,   # noqa: E402
                              _RULES_APPENDIX_2807)
from sender.ai_quota import build_ai_quota                     # noqa: E402
from sender.config import Config                               # noqa: E402
from sender.store import Store                                 # noqa: E402

МОДЕЛЬ = "claude-sonnet-4-6"
СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "6"))
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
ФАКТЫ = {"kc": load_facts(division="kc"), "meyer": load_facts(division="meyer")}

ЗАХОДЫ = ["от того, ЧТО они выпускают",
          "от оборудования и линий, которые у них стоят",
          "от сырья, с которым они работают",
          "от масштаба производства"]

СИСТЕМА = """Ты редактор холодных B2B-писем. Тебе дают ЧЕРНОВИК, собранный
механически: факты в нём верные, а формулировки шаблонные и повторяются от
письма к письму. Перепиши его своими словами.

ЖЁСТКО НЕЛЬЗЯ:
- добавлять факты, числа, названия и обещания, которых нет в черновике;
- убирать имя компании, вопрос в конце и строку «С уважением,»;
- писать «предлагаем», «скидка», «акция», «купить», «цена», «в наличии»,
  проценты и суммы;
- длинные тире «—», только дефис;
- писать от «мы»: поставляет компания, менеджер лично «подбираю/веду».

НАДО: живой человеческий тон, свои формулировки вместо шаблонных, тот же
смысл и та же длина. Первую фразу строй ИМЕННО так, как сказано в задании.

""" + _RULES_APPENDIX_2807 + """

ФОРМАТ ОТВЕТА - СТРОГО JSON без текста вокруг:
{"subject":"...","body":"..."}"""


def _без_чисел(т):
    т = re.sub(r"\d[\d\s.,-]*", "", str(т))
    return re.sub(r"\s{2,}", " ", т).strip(" ,;-")


def _первый(v, n=2):
    if not v:
        return ""
    сп = v if isinstance(v, list) else [x.strip() for x in str(v).split(";")]
    к = [_без_чисел(x) for x in сп if str(x).strip()]
    return ", ".join([x for x in к if len(x) > 3][:n]).lower()


def собрать(rec, п, div):
    имя = короткое_имя(getattr(rec, "company_name", "")) or "вашей компании"
    прод, лин = _первый(п.get("продукция"), 2), _первый(п.get("оборудование_линии"), 1)
    мощн, сыр = _первый(п.get("мощности"), 1), _первый(п.get("сырьё"), 2)
    набл = []
    if прод:
        набл.append(f"Смотрел, что выпускает «{имя}»: {прод}.")
    if лин:
        набл.append(f"На производстве {лин}.")
    elif мощн:
        набл.append(f"Заявленные мощности - {мощн}.")
    if div == "kc":
        предст = ("Я веду направление компрессорного оборудования в "
                  "Компрессор Центре - подбираю машины под конкретные задачи.")
        связка = ("Такое производство обычно завязано на сжатом воздухе: "
                  "пневмоприводы, обдув, подача инструмента. Винтовая пара "
                  "со временем изнашивается - падает производительность и "
                  "растёт расход электроэнергии при той же выработке.")
        вопрос = ("Подскажите, актуален ли для вас вопрос обновления или "
                  "расширения компрессорного парка?")
        тема = f"Вопрос по компрессорному парку в «{имя}»"
    else:
        предст = ("Меня зовут ИМЯ_ОТПРАВИТЕЛЯ, я веду направление "
                  "рентген-инспекции и фотосепарации в Meyer.")
        связка = ("В таком производстве инородное включение, попавшее в "
                  "готовый продукт, обходится дорого. Рентген-инспекция "
                  "видит их внутри упаковки, фотосепаратор снимает "
                  "посторонние фракции на потоке сырья.")
        if сыр:
            связка = f"Работаете с сырьём: {сыр}. " + связка
        вопрос = ("Подскажите, как сейчас закрыт контроль включений - на "
                  "сырье, на готовой продукции или нигде?")
        тема = f"Вопрос по контролю включений в «{имя}»"
    перес = ("Если этот вопрос ведёт кто-то другой, буду признателен, если "
             "перешлёте письмо коллеге.")
    тело = "\n\n".join(x for x in ["Добрый день!", предст, " ".join(набл),
                                   связка, вопрос, перес, "С уважением,"] if x)
    return тема, тело


ПОЛЯ = ("цитата", "продукция", "оборудование_линии", "сырьё", "масштаб", "мощности")
группы = store.recipient_groups().get("по_id") or {}
взяли, цена, чисто = 0, 0.0, 0
for rid, gr in sorted(группы.items()):
    if "Партия 935" not in gr or взяли >= СКОЛЬКО:
        continue
    rec = store.get_recipient(rid)
    if not rec or not getattr(rec, "inn", None):
        continue
    try:
        п = q._site_facts(rec.inn) or {}
        req = q._request(rec)
    except Exception:  # noqa: BLE001
        continue
    if sum(1 for к in ПОЛЯ if п.get(к)) < 4:
        continue
    div = str(req.get("target_division") or "kc")
    div = div if div in ("kc", "meyer") else "kc"
    тема, черновик = собрать(rec, п, div)
    заход = ЗАХОДЫ[взяли % len(ЗАХОДЫ)]
    задание = (f"ЗАХОД ПЕРВОЙ ФРАЗЫ: {заход}.\n\nЧЕРНОВИК:\n"
               f"ТЕМА: {тема}\n{черновик}")
    т0 = time.time()
    try:
        m = gen_provider._raw_stream([{"role": "user", "content": задание}],
                                     МОДЕЛЬ, 1200, thinking=False,
                                     effort="low", system=СИСТЕМА)
        т = "".join(b.text for b in m.content
                    if getattr(b, "type", "") == "text")
        u = getattr(m, "usage", None)
        c_ = ((int(getattr(u, "input_tokens", 0) or 0)
               + 1.25 * int(getattr(u, "cache_creation_input_tokens", 0) or 0)
               + 0.1 * int(getattr(u, "cache_read_input_tokens", 0) or 0)) / 1e6 * 3.0
              + int(getattr(u, "output_tokens", 0) or 0) / 1e6 * 15.0)
        цена += c_
        д = json.loads(re.search(r"\{.*\}", т, re.S).group(0))
        т2, б2 = str(д.get("subject") or тема), str(д.get("body") or "")
    except Exception as e:  # noqa: BLE001
        print("  сбой на %s: %s" % (getattr(rec, "company_name", ""), str(e)[:100]))
        continue
    взяли += 1
    плохо = gate(т2, б2, mode="GENERIC",
                 extra=dict(req.get("extra") or {},
                            company_name=getattr(rec, "company_name", "")),
                 facts=ФАКТЫ[div], division=div)
    if not плохо:
        чисто += 1
    print("\n" + "=" * 78)
    print("%s  [%s]  заход: %s" % (str(getattr(rec, "company_name", ""))[:40],
                                   div, заход))
    print("ТЕМА: %s" % т2)
    print("-" * 78)
    print(б2)
    print("-" * 78)
    print("гейт: %s | %.1fс | $%.4f"
          % ("ЧИСТО" if not плохо else "; ".join(str(x)[:110] for x in плохо),
             time.time() - т0, c_))

print("\n\n=== ИТОГ ===")
print("  писем: %d, прошли гейт: %d" % (взяли, чисто))
print("  цена всего: $%.3f, за письмо: $%.4f"
      % (цена, цена / взяли if взяли else 0))
