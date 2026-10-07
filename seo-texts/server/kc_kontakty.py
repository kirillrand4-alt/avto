# -*- coding: utf-8 -*-
r"""База КЦ, шаг 3: контакты, описание и ОКВЭД по каждой компании списка (kc-spisok.json).

Те же шаги, что для файлов Meyer, с правилом владельца 07.10 «только сайт или тендерные
площадки, номера с checko бесполезны»:
  1. checko-карточка (через прокси владельца) — только доп. ОКВЭД, если их нет (как в файле 4).
     Номера и сайт с checko не берём.
  2. Обход живого сайта (как cc_obhod): главная + «контакты/о компании/руководство» + страницы-
     источники наших контактов на том же домене; все номера на живых страницах; ИНН на странице
     (с контрольной суммой) — подтверждение, что сайт этой компании. Где перед номером есть подпись —
     модель по фрагменту говорит, чей номер (классы под КЦ: главный механик/энергетик отдельно).
  3. Описание по тексту сайта (модель): чем занимается, продукция.
  4. Закупки ЕИС (enrich_contacts.find_zakupki_contacts): контактные лица карточек, где ИНН
     компании на странице (компания — заказчик). Плюс карточки-источники из нашей базы.
Выход (fsync, резюм по ИНН): C:\sender\server\kc-kontakty.jsonl -> копия на дроп.
"""
import io
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import meyer_proverka as MP  # noqa: E402
import meyer_nalichie as MN  # noqa: E402
import cc_obhod as CO  # noqa: E402  (ТЕЛ, ДОБ, ИНН_RX, ПОДПИСЬ, инн_ок, норм, ссылки)
import cc_checko_proxy as CP  # noqa: E402
import verify_company as VC  # noqa: E402
import enrich_contacts as EC  # noqa: E402

ВЫХОД = os.path.join(DIR, 'kc-kontakty.jsonl')
_лок = threading.Lock()
КЛАССЫ = ('директор', 'технический директор', 'главный инженер', 'главный механик', 'главный энергетик',
          'инженер', 'производство', 'закупки', 'главный технолог', 'технолог', 'качество',
          'коммерческий директор', 'продажи', 'бухгалтерия', 'кадры', 'приёмная', 'общий', 'другое')
ПРОМПТ_НОМЕРА = (
    'Сайт компании {домен} ({название}). Страница: {url}\n'
    'Текст страницы вокруг телефонов:\n«««{текст}»»»\n\nНомера:\n{номера}\n\n'
    'Для КАЖДОГО номера по тексту рядом с ним: кому он принадлежит. Подпись (ФИО, должность, отдел) '
    'обычно стоит ПЕРЕД номером; номер соседа не приписывай; если подписи нет — пусто.\n'
    'Класс — строго одно из: ' + '|'.join(КЛАССЫ) + '. «директор» — только первое лицо или его '
    'заместитель; региональный/финансовый/коммерческий/по продажам/по развитию директор — не «директор». '
    '«инженер» — инженеры, механики, энергетики, КИПиА, ремонтные службы (не главные). '
    '«производство» — директор по производству, начальник производства/цеха. «закупки» — снабжение, '
    'закупки, МТО. «общий» — номер без подписи, общий, справочная, диспетчер, приём заказов.\n'
    'Сайт может быть сайтом группы компаний: «чей» — "эта", если номер относится к компании «{название}» '
    '(или это общий номер сайта без привязки к другому предприятию), "другая" — если по тексту номер другого '
    'завода/филиала/юрлица группы (другой город, другое название).\n'
    'Ответ — ТОЛЬКО JSON-массив: [{{"n":номер_в_списке,"фио":"…или пусто","должность":"как в тексте '
    'или пусто","класс":"…","чей":"эта|другая"}}]')
ПРОМПТ_ОПИС = (
    'Компания: {название} (ИНН {инн}), сайт {домен}. ОКВЭД основной: {оквэд}.\n'
    'Текст с сайта (главная, «о компании», продукция):\n«««{текст}»»»\n\n'
    'Ответ — ТОЛЬКО JSON без markdown: {{"описание":"1–2 предложения: чем занимается и что производит, '
    'по фактам с сайта, без рекламы","продукция":"через запятую, до 8 позиций","мощности":"объёмы/'
    'заводы/цеха, если названы на сайте, иначе пусто"}}')


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def модель(промпт, json_массив):
    for попытка in range(3):
        try:
            out = VC._provider_call_stdlib(промпт)
            if json_массив:
                return {int(x.get('n', 0)): x for x in json.loads(re.search(r'\[.*\]', out, re.S).group(0))
                        if isinstance(x, dict)}
            return json.loads(re.search(r'\{.*\}', out, re.S).group(0))
        except Exception:  # noqa: BLE001
            time.sleep(5 * (попытка + 1))
    return {}


ПРОКСИ = []
_пк = [0]


def checko(к):
    if not ПРОКСИ:
        return {}
    with _лок:
        п = ПРОКСИ[_пк[0] % len(ПРОКСИ)]
        _пк[0] += 1
    код, html = п.get('https://checko.ru/search?query=%s' % к['inn'])
    if код != 200:
        return {'checko': str(код)}
    т = CP.текст(html)
    сайт = re.search(r'Сайт\s+((?:https?://)?(?:www\.)?[a-zа-я0-9\-]+(?:\.[a-zа-я0-9\-]+)+)', т, re.I)
    return {'checko': 'ok', 'оквэд_все': CP.окведы(т)[:60], 'сайт': сайт.group(1) if сайт else ''}


def обход(к, сайт):
    старт = сайт if сайт.startswith('http') else 'https://' + сайт
    очередь = [старт] + [u for u in к.get('страницы_базы', []) if u.startswith('http')][:6]
    тексты, страницы = {}, []
    i = 0
    while i < len(очередь) and len(тексты) < 12:
        u = очередь[i]
        i += 1
        ст, html, _ = MN.скачать(u)
        страницы.append([u, ст])
        if ст != 'ok':
            continue
        тексты[u] = MP.в_текст(html)
        if i == 1:
            for л in CO.ссылки(u, html)[:8]:
                if л not in очередь:
                    очередь.append(л)
    номера = {}
    for u, т in тексты.items():
        for м in CO.ТЕЛ.finditer(т):
            н = CO.норм(м.group(0))
            if not н:
                continue
            доб = CO.ДОБ.match(т[м.end():м.end() + 20])
            ключ = н + ((' доб. ' + доб.group(1)) if доб else '')
            з = номера.setdefault(ключ, {'номер': н, 'доб': доб.group(1) if доб else '', 'страницы': [],
                                         'контекст': re.sub(r'\s+', ' ', т[max(0, м.start() - 200):м.end() + 60]),
                                         '_поз': (u, м.start())})
            if u not in з['страницы']:
                з['страницы'].append(u)
        for м in re.finditer(r'\[tel:([^\]]+)\]', т):
            н = CO.норм(м.group(1))
            if н and not any(з['номер'] == н for з in номера.values()):
                номера[н] = {'номер': н, 'доб': '', 'страницы': [u],
                             'контекст': re.sub(r'\s+', ' ', т[max(0, м.start() - 200):м.end() + 60]), '_поз': (u, м.start())}
    по_стр = {}
    for ключ, з in номера.items():
        u, п = з['_поз']
        if CO.ПОДПИСЬ.search(тексты[u][max(0, п - 160):п]):
            по_стр.setdefault(u, []).append(ключ)
    for u, ключи in по_стр.items():
        for k in range(0, len(ключи), 14):
            кусок = ключи[k:k + 14]
            т = тексты[u]
            окна = sorted((max(0, номера[кл]['_поз'][1] - 400), номера[кл]['_поз'][1] + 150) for кл in кусок)
            слито = []
            for a, b in окна:
                if слито and a <= слито[-1][1]:
                    слито[-1] = (слито[-1][0], max(b, слито[-1][1]))
                else:
                    слито.append((a, b))
            ответ = модель(ПРОМПТ_НОМЕРА.format(домен=MN.домен(старт), название=к['имя'], url=u,
                                                текст='\n…\n'.join(т[a:b] for a, b in слито)[:6500],
                                                номера='\n'.join('%d. %s' % (j + 1, н) for j, н in enumerate(кусок))), True)
            for j, кл in enumerate(кусок):
                x = ответ.get(j + 1) or {}
                номера[кл].update({'фио': (x.get('фио') or '')[:80], 'должность': (x.get('должность') or '')[:120],
                                   'класс': x.get('класс') if x.get('класс') in КЛАССЫ else '',
                                   'чей': x.get('чей') if x.get('чей') in ('эта', 'другая') else ''})
    for з in номера.values():
        з.pop('_поз', None)
    инн_живой = []
    for т in тексты.values():
        for м in CO.ИНН_RX.finditer(т):
            if CO.инн_ок(м.group(1)) and м.group(1) not in инн_живой:
                инн_живой.append(м.group(1))
    # описание: главная и «о компании»/«продукция»
    кусочки = []
    for u, т in list(тексты.items())[:5]:
        т = re.sub(r'\[tel:[^\]]*\]', ' ', т)
        т = re.sub(r'\n\s*\S{1,25}\s*(?=\n)', '\n', т)
        кусочки.append(re.sub(r'\s+', ' ', т)[:2200])
    опис = модель(ПРОМПТ_ОПИС.format(название=к['имя'], инн=к['inn'], домен=MN.домен(старт), оквэд=к['осн'],
                                     текст='\n---\n'.join(кусочки)[:8000]), False) if кусочки else {}
    return {'сайт': старт, 'страницы': страницы, 'номера': list(номера.values()), 'инн_живой': инн_живой,
            'описание': опис.get('описание', ''), 'продукция': опис.get('продукция', ''), 'мощности': опис.get('мощности', '')}


def закупки(к):
    out = []
    r = EC.find_zakupki_contacts(к['inn'], max_cards=10) or {}
    if r.get('error'):
        out.append({'ошибка': r['error']})
    for card in r.get('cards', []):
        out.append({'url': card.get('url'), 'предмет': card.get('subject') or card.get('title'),
                    'инн_на_странице': card.get('inn_на_странице'), 'люди': card.get('people') or [],
                    'ошибка': card.get('error', '')})
    # карточки-источники из нашей базы: живая страница, ИНН и люди
    for url in (к.get('закупки_базы') or [])[:6]:
        if any(x.get('url') == url for x in out):
            continue
        try:
            h = EC._eis_get(url)
            txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)))
            out.append({'url': url, 'предмет': '', 'инн_на_странице': к['inn'] in txt, 'люди': EC._eis_people(txt),
                        'из_базы': True})
        except Exception as e:  # noqa: BLE001
            out.append({'url': url, 'ошибка': repr(e)[:80], 'из_базы': True})
        time.sleep(1.5)
    return out


def одна(к):
    з = {'inn': к['inn']}
    try:
        сайт = к['сайт']  # только сайт из нашей базы/таблицы CC, как в файлах 1–4 (без сайта из checko)
        if len(к.get('все') or []) <= 1:
            з['checko'] = checko(к)  # доп. ОКВЭД, как в файле 4
        if сайт:
            з.update(обход(к, сайт))
        з['закупки'] = закупки(к)
        з['итог'] = 'ok'
    except Exception as e:  # noqa: BLE001
        з['итог'] = 'сбой: ' + repr(e)[:120]
    записать(з)


def main():
    сп = json.load(io.open(os.path.join(DIR, 'kc-spisok.json'), encoding='utf-8'))['компании']
    сделано = set()
    if os.path.exists(ВЫХОД):
        for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
                if з.get('итог') == 'ok':
                    сделано.add(з['inn'])
            except ValueError:
                pass
    очередь = sorted((к for i, к in сп.items() if i not in сделано), key=lambda к: -к['выручка'])
    ПРОКСИ.extend(п for п in (CP.Прокси(x) for x in json.load(open(os.path.join(DIR, 'checko-proxies.json'))))
                  if п.get('https://checko.ru/')[0] == 200)
    print('компаний', len(сп), 'в очереди', len(очередь), 'прокси', len(ПРОКСИ), flush=True)
    t0 = time.time()
    n = [0]

    def один(к):
        одна(к)
        n[0] += 1
        if n[0] % 20 == 0:
            print('готово %d/%d за %d мин' % (n[0], len(очередь), (time.time() - t0) / 60), flush=True)

    with ThreadPoolExecutor(6) as ex:
        list(ex.map(один, очередь))
    shutil.copyfile(ВЫХОД, r'C:\seostat\drop\drop-storage\kc-kontakty.jsonl')
    print('готово', flush=True)


if __name__ == '__main__':
    main()
