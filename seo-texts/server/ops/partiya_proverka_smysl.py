# -*- coding: utf-8 -*-
"""Смысловая часть сплошной проверки: по каждому письму, через провайдера.

Механика уже сказала, что доказуемо кодом (адрес на странице, бренды,
числа, гейт). Здесь то, что кодом не проверить:

  1. компания действительно занимается тем, что ей приписали в письме;
  2. роль и человек контакта не выдуманы - подтверждаются текстом страницы,
     на которой адрес найден;
  3. письмо не приписывает получателю оборудование и участки, которых в
     паспорте нет (та самая ошибка, из-за которой правилась карточка);
  4. новостной повод, если он есть, соответствует тому, что в карточке.

Проверяющему дают ТОЛЬКО факты: карточку, кусок страницы-источника и само
письмо. Приговор структурный, без свободного сочинения.

Резюмируемо: журнал durable, повторный запуск добивает остаток.
Самоограничение по времени - серверное задание режется на 1800с.
"""
import io
import json
import os
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r"C:\sender")
import gen_provider                                            # noqa: E402
from sender.ai_letter import _recipient_block                  # noqa: E402
from sender.ai_quota import build_ai_quota                     # noqa: E402
from sender.config import Config                               # noqa: E402
from sender.store import Store                                 # noqa: E402

МОДЕЛЬ = "claude-opus-4-8"
ЦЕНА = (6.0, 30.0)
МЕХАНИКА = r"C:\sender\_ops\proverka-partii-mehanika.jsonl"
ЖУРНАЛ = r"C:\sender\_ops\proverka-partii-smysl.jsonl"
ПОТОКОВ = 5
СТАРТ = time.time()
ЛИМИТ_СЕК = (int(sys.argv[1]) if len(sys.argv) > 1 else 1650) - 120

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

сделано = set()
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            сделано.add(int(json.loads(s)["review_id"]))
        except Exception:
            pass

цели = []
for s in (io.open(МЕХАНИКА, encoding="utf-8")
          if os.path.exists(МЕХАНИКА) else []):
    try:
        z = json.loads(s)
    except Exception:
        continue
    if int(z["review_id"]) not in сделано:
        цели.append(z)
print(f"к смысловой проверке: {len(цели)} (уже проверено {len(сделано)})")
if not цели:
    raise SystemExit(0)

ФОРМА = """Ты проверяешь холодное письмо перед отправкой живому предприятию.
Твоя работа - поймать ЛОЖЬ и НЕСТЫКОВКИ, а не улучшить стиль.

=== КАРТОЧКА ПОЛУЧАТЕЛЯ (единственный источник правды о нём) ===
{карточка}

=== СТРАНИЦА, НА КОТОРОЙ НАЙДЕН АДРЕС {email} ===
источник: {url}
роль по нашим данным: {роль}
человек по нашим данным: {человек}
текст страницы (фрагмент):
{страница}

=== ПИСЬМО ===
ТЕМА: {тема}
{тело}

=== ЧТО ПРОВЕРИТЬ ===
1. profil: правда ли компания занимается тем, чем её занятие названо в
   письме? Сверяй с карточкой, не с общими соображениями.
2. vydumka: есть ли в письме утверждения о ЕГО производстве, которых нет в
   карточке? Особенно участки, цеха, оборудование, объёмы. Наша догадка по
   отрасли, поданная как факт о нём - это выдумка.
3. rol: подтверждает ли текст страницы роль и человека, указанных выше?
   Если на странице этого адреса нет или он подписан иначе - скажи.
4. povod: если письмо ссылается на новость или событие - есть ли оно в
   карточке? Если новости в карточке нет, а в письме есть - это выдумка.
5. prochee: любая другая нестыковка, из-за которой получатель поймёт, что
   письмо написано не про него.

Отвечай ТОЛЬКО JSON, без пояснений вокруг:
{{"profil": "ок|мимо|неясно", "vydumka": ["дословная цитата из письма", ...],
  "rol": "подтверждена|не подтверждена|нет данных",
  "povod": "ок|выдуман|нет повода",
  "prochee": ["короткая формулировка", ...],
  "verdikt": "отправлять|править|не отправлять",
  "pochemu": "одна фраза"}}"""

замок = threading.Lock()
итоги = []


def кусок_stranicy(inn, url, email):
    import gzip
    путь = os.path.join(r"C:\seostat\drop\pagecache", f"{inn}.json.gz")
    if not os.path.exists(путь):
        return "(страницы в кеше нет)"
    try:
        with gzip.open(путь, "rt", encoding="utf-8") as f:
            blob = json.load(f)
    except Exception:                                          # noqa: BLE001
        return "(кеш не читается)"
    for p in (blob.get("pages") or []):
        if str(p.get("url") or "") != url:
            continue
        html = p.get("html") or ""
        txt = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
        txt = re.sub(r"(?s)<[^>]+>", " ", txt)
        txt = re.sub(r"\s+", " ", txt)
        i = txt.lower().find(email)
        if i >= 0:
            return txt[max(0, i - 700):i + 700]
        return txt[:1400]
    return "(страницы источника нет в кеше)"


def один(z):
    rid = int(z["review_id"])
    r = store.confirm_get(rid) or {}
    rec = store.get_recipient(r.get("recipient_id"))
    div = str(z.get("направление") or "kc")
    try:
        req = q._request(rec)
        req["target_division"] = div
        карточка = _recipient_block(0, req, div, 0)
    except Exception as e:                                     # noqa: BLE001
        карточка = f"(карточка не собралась: {str(e)[:80]})"
    prompt = ФОРМА.format(
        карточка=карточка[:6000], email=z.get("email", ""),
        url=z.get("источник", "") or "(нет)", роль=z.get("роль", "") or "(нет)",
        человек=z.get("человек", "") or "(нет)",
        страница=кусок_stranicy(z.get("inn", ""), z.get("источник", ""),
                                z.get("email", ""))[:1600],
        тема=r.get("subject", ""), тело=r.get("body", ""))

    расход = {"in": 0, "out": 0}
    ответ, посл = None, None
    for i in range(3):
        try:
            m = gen_provider._raw_stream(
                [{"role": "user", "content": prompt}], МОДЕЛЬ, 1500,
                thinking=False, effort="medium")
            т = "".join(b.text for b in m.content
                        if getattr(b, "type", "") == "text")
            u = getattr(m, "usage", None)
            расход["in"] += int(getattr(u, "input_tokens", 0) or 0)
            расход["out"] += int(getattr(u, "output_tokens", 0) or 0)
            чист = re.sub(r"^\s*```[a-zA-Z]*|```\s*$", "", т.strip())
            i0, i1 = чист.find("{"), чист.rfind("}")
            ответ = json.loads(чист[i0:i1 + 1])
            break
        except Exception as e:                                 # noqa: BLE001
            посл = e
            time.sleep(min(15, 2 ** i))

    зап = {"review_id": rid, "компания": z.get("компания"),
           "направление": div, "email": z.get("email"),
           "контакт_механика": z.get("контакт"),
           "цена_$": round(расход["in"] / 1e6 * ЦЕНА[0]
                           + расход["out"] / 1e6 * ЦЕНА[1], 4),
           "ts": int(time.time())}
    if ответ is None:
        зап["сбой"] = str(посл)[:140]
    else:
        зап.update({k: ответ.get(k) for k in
                    ("profil", "vydumka", "rol", "povod", "prochee",
                     "verdikt", "pochemu")})
    with замок:
        итоги.append(зап)
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
            f.write(json.dumps(зап, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    print(f"  [{len(итоги)}/{len(цели)}] #{rid} "
          f"{str(зап.get('компания'))[:28]:<30} "
          f"{зап.get('verdikt') or 'СБОЙ':<14} {str(зап.get('pochemu'))[:60]}")


ЧАНК = 10
for нач in range(0, len(цели), ЧАНК):
    if time.time() - СТАРТ > ЛИМИТ_СЕК:
        print(f"\nвремя вышло на {нач} из {len(цели)} - добьёт следующий круг")
        break
    with ThreadPoolExecutor(max_workers=ПОТОКОВ) as pool:
        list(pool.map(один, цели[нач:нач + ЧАНК]))

в = Counter(str(x.get("verdikt") or "сбой") for x in итоги)
print(f"\nвердикты: {dict(в)} | ${sum(x['цена_$'] for x in итоги):.2f}")
