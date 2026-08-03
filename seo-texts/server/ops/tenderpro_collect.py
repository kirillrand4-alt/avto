# -*- coding: utf-8 -*-
r"""Tender.pro: сбор сырья по базе (компания -> тендеры -> текст комментария).

Контакт на Tender.pro лежит СВОБОДНЫМ ТЕКСТОМ в блоке «Комментарий:», поэтому
здесь мы только СОБИРАЕМ текст с доказанной привязкой, а разбор ФИО/должностей
отдаём провайдеру отдельной стадией (правило владельца: тяжёлую работу — через
провайдерский API).

ПРИВЯЗКА закрыта по умолчанию: ИНН обязан найтись на странице компании
(«ИНН/КПП 1234567890/123456789»), а организатор тендера — совпасть с той же
карточкой компании. Не совпало — пропускаем.

СВЕЖЕСТЬ: >3 лет не берём вовсе, 2–3 года помечаем «устаревший».

Durable: C:\seostat\drop\drop-storage\tp_raw.json (накопитель, fsync)
       + C:\seostat\drop\tp_collect_stream.jsonl (по компании, fsync).
Резюмируемо: обработанные ИНН пропускаются.
"""
import io
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                 urllib.request.HTTPSHandler(context=ctx))
B = 'https://www.tender.pro'
ВЫХ = r'C:\seostat\drop\drop-storage\tp_raw.json'
ПОТОК = r'C:\seostat\drop\tp_collect_stream.jsonl'
БЮДЖЕТ = float(sys.argv[1]) if len(sys.argv) > 1 else 300.0
ЛИМИТ = int(sys.argv[2]) if len(sys.argv) > 2 else 0
НАЧАЛО = time.time()
СЕЙЧАС = time.time()
ГОД = 365.25 * 86400
ПРЕДЕЛ_ЛЕТ, УСТАР_ЛЕТ = 3.0, 2.0
КАРТ_НА_КОМПАНИЮ = 12


def дай(u, t=45):
    r = urllib.request.Request(u, headers={'User-Agent': UA,
                                           'Accept-Language': 'ru-RU,ru'})
    with OP.open(r, timeout=t) as f:
        return EC._раскодировать(f.read(), f.headers.get('Content-Type', ''))


def лет(д):
    m = re.match(r'(\d{2})\.(\d{2})\.(\d{4})', str(д or ''))
    if not m:
        return None
    try:
        t = time.mktime((int(m.group(3)), int(m.group(2)), int(m.group(1)),
                         12, 0, 0, 0, 1, -1))
    except Exception:  # noqa: BLE001
        return None
    return (СЕЙЧАС - t) / ГОД


def свеж(л):
    if л is None:
        return 'неизвестна'
    return 'свежий' if л <= УСТАР_ЛЕТ else ('устаревший' if л <= ПРЕДЕЛ_ЛЕТ
                                            else 'просрочен')


def компания(inn):
    try:
        h = дай(f'{B}/api/companies/list?search_type=company&inn={inn}')
    except Exception:  # noqa: BLE001
        return None, ''
    f = re.findall(r'company-card__name "><a href="/api/company/(\d+)/view[^"]*"'
                   r'[^>]*>([^<]{0,90})</a>', h)
    return (f[0][0], f[0][1].strip()) if f else (None, '')


def тендеры(cid, inn):
    try:
        h = дай(f'{B}/api/company/{cid}/view?active_tab=purchases'
                f'&tender_state=100&by=200', t=60)
    except Exception:  # noqa: BLE001
        return [], False
    плоско = re.sub(r'<[^>]+>', ' ', h)
    подтв = str(inn) in re.findall(r'(?<!\d)(\d{10,12})(?:/\d{9})', плоско)
    строки = []
    for blk in h.split('<li class="tender-list__item')[1:]:
        m = re.search(r'href="/api/tender/(\d+)/view_public"[^>]*>\s*(.{0,220}?)</a>',
                      blk, re.S)
        if not m:
            continue
        d = re.search(r'Создан:</span>&nbsp;<span class="c-text">([\d.]+)</span>', blk)
        строки.append({'id': m.group(1), 'дата': d.group(1) if d else '',
                       'имя': re.sub(r'\s+', ' ',
                                     re.sub(r'<[^>]+>', '', m.group(2))).strip()[:150]})
    return строки, подтв


# Маркеры блока с контактным лицом. «Ответственное должностное лицо по
# техническому вопросу» — устойчивый оборот Tender.pro, он отделяет технаря от
# снабженца прямо в тексте, и это лучший признак, что мы видели.
_КОНТАКТНОЕ = re.compile(
    r'ответственн\w*\s+должностн\w*\s+лиц|контактн\w*\s+лиц|'
    r'по\s+техническ\w*\s+вопрос|по\s+вопросам\s+техническ|'
    r'исполнител[ьяю]\b|телефон\w*\s+для\s+справок|'
    r'(?:главн\w*|ведущ\w*)\s+(?:инженер|механик|энергетик|технолог)',
    re.I)


def карточка(tid):
    try:
        h = дай(f'{B}/api/tender/{tid}/view_public')
    except Exception:  # noqa: BLE001
        return None
    org = re.search(r'Организатор конкурса:</div><!-- div --><a '
                    r'href="/api/company/(\d+)/view"[^>]*title="([^"]{0,220})"', h)
    cm = re.search(r'Комментарий:</div><!-- div -->(.*?)</div><!-- div --></div>',
                   h, re.S)
    c = cm.group(1) if cm else ''
    c = re.sub(r'<br\s*/?>', '\n', c)
    c = re.sub(r'</p>', '\n', c)
    c = re.sub(r'<[^>]+>', ' ', c)
    c = (c.replace('&nbsp;', ' ').replace('&quot;', '"').replace('&amp;', '&')
         .replace('&mdash;', '—').replace('&laquo;', '«').replace('&raquo;', '»'))
    c = re.sub(r'[ \t]+', ' ', c).strip()
    m = re.search(r'По вопросам регистрации|Заявки принимаются строго через ЭТП|'
                  r'Вы вправе предоставить любую информацию', c)
    без_боилерплейта = c[:m.start()] if m else c
    # ОБРЕЗКА РЕЗАЛА РОВНО ТО, РАДИ ЧЕГО ИСТОЧНИК И БЕРЁТСЯ. Tender.pro —
    # единственный канал, где встречается связка «технический руководитель +
    # прямой мобильный»: «Ответственное должностное лицо по техническому
    # вопросу: Главный механик Крюков Олег Викторович, +7 (926) 087-30-86».
    # Такой блок стоит в КОНЦЕ комментария, после описания предмета закупки, —
    # то есть за 3000-м символом у длинных карточек его просто не было.
    #
    # Лечим двумя способами сразу: поднимаем потолок и, независимо от него,
    # ВЫДЁРГИВАЕМ куски с контактным лицом из ПОЛНОГО текста и приклеиваем,
    # если они не попали. Потолок один не спасёт: карточка бывает и на 20 КБ.
    ядро = без_боилерплейта[:8000]
    хвосты = []
    for мм in _КОНТАКТНОЕ.finditer(без_боилерплейта):
        кусок = без_боилерплейта[мм.start():мм.start() + 400].strip()
        if кусок and кусок not in ядро:
            хвосты.append(кусок)
    if хвосты:
        ядро = ядро + '\n\n[контактные блоки из полного текста]\n' + \
            '\n'.join(хвосты[:6])
    return {'org_id': org.group(1) if org else '', 'org': org.group(2) if org else '',
            'комментарий': ядро}


накоп = {}
if os.path.exists(ВЫХ):
    try:
        накоп = json.load(open(ВЫХ, encoding='utf-8'))
    except Exception:  # noqa: BLE001
        накоп = {}
накоп.setdefault('компании', {})
накоп.setdefault('карточки', [])
сдел = set(накоп['компании'])

сп, вид = [], set()
# ЦЕЛИ БЫЛИ ЗАШИТЫ ДВУМЯ ФАЙЛАМИ — core396.json (396 центробежных) и
# sales_base.json (555 продажников), в сумме 936 при 1573 в панели. То есть
# больше шестисот предприятий у Tender.pro не спрашивались ни разу, а это
# единственный канал со связкой «технарь + прямой мобильный».
#
# Теперь список задаётся снаружи (--inn, --targets, --iz-paneli), а прежние
# два файла остаются умолчанием: менять его молча нельзя.
sys.path.insert(0, r'C:\sender\server')
import celi_obshchie as ЦЕЛИ  # noqa: E402
_инны, _откуда = ЦЕЛИ.выбрать(печатать=True)
for i in _инны:
    if i and i not in вид:
        вид.add(i)
        сп.append({'inn': i, 'name': '', 'rev': 0})

todo = [c for c in сп if c['inn'] not in сдел]
if ЛИМИТ:
    todo = todo[:ЛИМИТ]
ст = {'база': len(сп), 'сделано_ранее': len(сдел), 'в_очереди': len(todo),
      'обработано': 0, 'есть_карточка': 0, 'инн_подтв': 0, 'с_тендерами': 0,
      'годных_тендеров': 0, 'открыто_карточек': 0, 'с_текстом_контакта': 0}
print('СТАРТ ' + json.dumps(ст, ensure_ascii=False), flush=True)
замок = threading.Lock()
ф = io.open(ПОТОК, 'a', encoding='utf-8')
КОНТАКТ = re.compile(r'@[\w\-]+\.[a-z]{2,}|(?:\+7|8)[\s\-(]*\d{3,5}[\s\-)]*\d{2,3}', re.I)


def работа(c):
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        return
    inn = c['inn']
    зап = {'inn': inn, 'name': c['name'][:80], 'card': 0}
    новые = []
    try:
        cid, имя = компания(inn)
        if cid:
            зап.update({'card': 1, 'cid': cid, 'tp_name': имя})
            строки, подтв = тендеры(cid, inn)
            зап['подтв'] = подтв
            зап['тендеров'] = len(строки)
            if подтв and строки:
                годн = []
                for s in строки:
                    л = лет(s['дата'])
                    if л is not None and л > ПРЕДЕЛ_ЛЕТ:
                        continue
                    годн.append((л if л is not None else 99, s))
                годн.sort(key=lambda x: x[0])
                зап['годных'] = len(годн)
                for л, s in годн[:КАРТ_НА_КОМПАНИЮ]:
                    if time.time() - НАЧАЛО > БЮДЖЕТ:
                        break
                    k = карточка(s['id'])
                    зап['открыто'] = зап.get('открыто', 0) + 1
                    if not k:
                        continue
                    if k['org_id'] and k['org_id'] != str(cid):
                        continue                      # организатор чужой
                    if not КОНТАКТ.search(k['комментарий']):
                        continue
                    новые.append({
                        'inn': inn, 'company': c['name'][:100],
                        'tender_id': s['id'],
                        'url': f'{B}/api/tender/{s["id"]}/view_public',
                        'дата': s['дата'], 'лет': round(л, 2) if л != 99 else None,
                        'свежесть': свеж(л if л != 99 else None),
                        'предмет': s['имя'][:180], 'организатор': k['org'][:120],
                        'comment': k['комментарий']})
    except Exception as ex:  # noqa: BLE001
        зап['err'] = repr(ex)[:110]
    with замок:
        накоп['компании'][inn] = зап
        накоп['карточки'] += новые
        ф.write(json.dumps(зап, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())
        ст['обработано'] += 1
        ст['есть_карточка'] += зап.get('card', 0)
        ст['инн_подтв'] += 1 if зап.get('подтв') else 0
        ст['с_тендерами'] += 1 if зап.get('тендеров') else 0
        ст['годных_тендеров'] += зап.get('годных', 0)
        ст['открыто_карточек'] += зап.get('открыто', 0)
        ст['с_текстом_контакта'] += len(новые)
        if ст['обработано'] % 50 == 0:
            with open(ВЫХ, 'w', encoding='utf-8') as f:
                json.dump(накоп, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            print('.. ' + json.dumps(ст, ensure_ascii=False), flush=True)


with ThreadPoolExecutor(max_workers=6) as пул:
    list(пул.map(работа, todo))
ф.close()
with open(ВЫХ, 'w', encoding='utf-8') as f:
    json.dump(накоп, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
ст['всего_сырья'] = len(накоп['карточки'])
ст['секунд'] = round(time.time() - НАЧАЛО, 1)
print('ИТОГ ' + json.dumps(ст, ensure_ascii=False), flush=True)
os._exit(0)
