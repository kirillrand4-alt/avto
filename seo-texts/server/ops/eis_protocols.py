# -*- coding: utf-8 -*-
"""Состав закупочной комиссии из ПРОТОКОЛОВ и печатных форм ЕИС.

Почему это отдельный источник, а не «ещё одни документы».

Извещение называет контрактного управляющего — это снабженец. А ПРОТОКОЛ
заседания закупочной комиссии перечисляет её состав ПОИМЁННО и с должностями,
и в комиссии по закупке оборудования почти всегда сидит технарь: главный
инженер, главный энергетик, начальник производства. Это то самое лицо, которое
решает, ЧТО покупать, а не оформляет уже принятое решение.

Три пути к тексту, от дешёвого к дорогому:
  1. ПЕЧАТНАЯ ФОРМА извещения (printForm): один HTTP-запрос, отдаёт поля
     карточки целиком, включая контактных лиц, которых обычная страница
     прячет за JS;
  2. документы карточки, где в имени файла есть «протокол»;
  3. остальные документы — только если протоколов не нашлось.

Читаем docx, rtf и PDF (PDF появился 29.07 — до этого протоколы в PDF
пропускались молча, а их большинство).

Телефоны берём ТОЛЬКО из окрестности имени члена комиссии или секретаря. В
протоколе есть и телефоны УЧАСТНИКОВ — это другие компании, поставщики, и
записывать их заказчику нельзя: получится ровно та подмена, на которой мы уже
обожглись с чужим работодателем на hh.

Резюмируемо: eis_protocols_stream.jsonl. По умолчанию СУХОЙ ПРОГОН.
Запуск: python eis_protocols.py [бюджет_сек] [--apply] [--inn ИНН] [--limit N]
"""
import io
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB          # noqa: E402
import enrich_contacts as EC     # noqa: E402

_поз = [a for a in sys.argv[1:] if not a.startswith('--')]
БЮДЖЕТ = float(_поз[0]) if _поз else 1500.0
ПРИМЕНИТЬ = '--apply' in sys.argv
ОДИН = (sys.argv[sys.argv.index('--inn') + 1] if '--inn' in sys.argv else '')
ЛИМИТ = int(sys.argv[sys.argv.index('--limit') + 1]
            if '--limit' in sys.argv else 100000)
ПОТОК = r'C:\seostat\drop\eis_protocols_stream.jsonl'
НАЧАЛО = time.time()
КАРТОЧЕК = 5
ФАЙЛОВ = 4

db = EDB.EnrichDB()
e = db.cx

_ПРОТОКОЛ = re.compile(r'протокол', re.I)
_КОМИССИЯ = re.compile(r'комисси|состав\s+комисси|председател|секретар|член\w*\s+комисси',
                       re.I)


def провайдер(промпт, максимум=1800):
    key = os.environ.get('PROVIDER_API_KEY', '')
    if not key:
        return ''
    base = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
    тело = json.dumps({'model': 'claude-fable-5', 'max_tokens': максимум,
                       'stream': True,
                       'messages': [{'role': 'user', 'content': промпт}]},
                      ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        base + '/v1/messages', data=тело, method='POST',
        headers={'x-api-key': key, 'anthropic-version': '2023-06-01',
                 'content-type': 'application/json',
                 'accept': 'text/event-stream', 'User-Agent': 'curl/8.5.0'})
    куски = []
    with urllib.request.urlopen(req, timeout=280) as r:
        for сырая in r:
            стр = сырая.decode('utf-8', 'replace').strip()
            if not стр.startswith('data:'):
                continue
            try:
                ev = json.loads(стр[5:].strip())
            except Exception:  # noqa: BLE001
                continue
            if ev.get('type') == 'content_block_delta':
                куски.append((ev.get('delta') or {}).get('text', ''))
    return ''.join(куски)


def печатная_форма(url):
    """Текст печатной формы извещения. Один запрос вместо обхода вкладок.

    Адрес карточки несёт regNumber, а печатная форма живёт по предсказуемому
    пути. Формы у 44-ФЗ и 223-ФЗ разные, поэтому пробуем обе — лишний
    неудачный запрос дешевле пропущенного источника.
    """
    m = re.search(r'regNumber=(\d+)', url or '')
    if not m:
        return '', ''
    рег = m.group(1)
    for шаблон in (
        'https://zakupki.gov.ru/epz/order/notice/printForm/view.html?regNumber=',
        'https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=',
        'https://zakupki.gov.ru/epz/order/notice/printForm/viewXml.html?regNumber=',
    ):
        try:
            h = EC._eis_get(шаблон + рег)
        except Exception:  # noqa: BLE001
            continue
        if not h or len(h) < 800:
            continue
        t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))
        if len(t) > 400:
            return t, шаблон + рег
        time.sleep(0.5)
    return '', ''


def куски_комиссии(текст, окно=900):
    """Окрестности слов про комиссию: остальное в протоколе — суммы и лоты."""
    из = []
    for m in _КОМИССИЯ.finditer(текст or ''):
        из.append(текст[max(0, m.start() - 200):m.end() + окно])
        if len(из) >= 6:
            break
    return из


def разобрать(текст, имя_компании, inn, ссылка):
    """ФИО + должность членов комиссии. Разбор моделью: формат протокола у
    каждого заказчика свой — таблица, список, сплошной абзац."""
    куски = куски_комиссии(текст)
    if not куски:
        return []
    промпт = (
        f'Ниже куски протокола закупочной комиссии заказчика «{имя_компании}» '
        f'(ИНН {inn}). Выпиши ЧЛЕНОВ КОМИССИИ этого заказчика: председателя, '
        'заместителя, секретаря и рядовых членов — с ДОЛЖНОСТЯМИ так, как они '
        'написаны. НЕ включай представителей участников закупки и другие '
        'организации: они в протоколе тоже есть, но это поставщики, а не '
        'сотрудники заказчика. Телефон указывай, только если он стоит рядом с '
        'ФИО этого человека. ФИО в именительном падеже. Верни СТРОГО JSON без '
        'markdown: {"people":[{"person":"Фамилия И.О. или полностью",'
        '"post":"должность","phone":"телефон или пустая строка",'
        '"role_in_commission":"председатель|секретарь|член"}]}\n\n'
        + '\n…\n'.join(куски)[:16000])
    try:
        ответ = провайдер(промпт)
    except Exception:  # noqa: BLE001
        return []
    m = re.search(r'\{.*\}', ответ or '', re.S)
    if not m:
        return []
    try:
        данные = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return []
    из = []
    for ч in (данные.get('people') or []):
        фио = (ч.get('person') or '').strip()
        пост = (ч.get('post') or '').strip()
        if not фио:
            continue
        из.append({'person': фио, 'post': пост,
                   'phone': (ч.get('phone') or '').strip(),
                   'in_commission': (ч.get('role_in_commission') or '').strip(),
                   'url': ссылка})
    return из


def цели():
    if ОДИН:
        return [ОДИН]
    из, было = [], set()
    БАЗА = json.load(open(r'C:\sender\_ops\sales_base.json', encoding='utf-8'))
    for строки in БАЗА.values():
        for x in строки:
            i = str(x.get('inn') or '').strip()
            if i and i not in было:
                было.add(i)
                из.append(i)
    сделано = set()
    if os.path.exists(ПОТОК):
        for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
            try:
                j = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if not j.get('err'):
                сделано.add(str(j.get('inn')))
    return [i for i in из if i not in сделано][:ЛИМИТ]


def main():
    todo = цели()
    out = {'целей': len(todo), 'пройдено': 0, 'карточек': 0, 'печатных_форм': 0,
           'протоколов_файлов': 0, 'прочитано_pdf': 0, 'людей': 0, 'техЛПР': 0,
           'телефонов': 0, 'ошибок': 0,
           'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой прогон (--apply)',
           'примеры': []}
    ф = io.open(ПОТОК, 'a', encoding='utf-8')
    for inn in todo:
        if time.time() - НАЧАЛО > БЮДЖЕТ:
            break
        итог = {'inn': inn}
        try:
            имя_к = (e.execute('SELECT name FROM companies WHERE inn=?',
                               (inn,)).fetchone() or [''])[0] or ''
            z = EC.find_zakupki_contacts(inn, max_cards=КАРТОЧЕК)
            люди = []
            for c in ((z or {}).get('cards') or [])[:КАРТОЧЕК]:
                if time.time() - НАЧАЛО > БЮДЖЕТ:
                    break
                out['карточек'] += 1
                url = c.get('url') or ''
                # 1) печатная форма
                t, пф = печатная_форма(url)
                if t:
                    out['печатных_форм'] += 1
                    люди += разобрать(t, имя_к, inn, пф)
                # 2) файлы-протоколы, затем прочие
                файлы = EC.eis_documents(url)
                прот = [f for f in файлы if _ПРОТОКОЛ.search(f[0] or '')]
                прочие = [f for f in файлы if f not in прот]
                for имя_ф, у in (прот + прочие)[:ФАЙЛОВ]:
                    if time.time() - НАЧАЛО > БЮДЖЕТ:
                        break
                    txt = EC.doc_text(у)
                    if not txt:
                        continue
                    if re.search(r'\.pdf', имя_ф or '', re.I):
                        out['прочитано_pdf'] += 1
                    if _ПРОТОКОЛ.search(имя_ф or ''):
                        out['протоколов_файлов'] += 1
                    люди += разобрать(txt, имя_к, inn, у)
                    time.sleep(0.5)
            # схлопываем по ФИО: один человек попадает и в форму, и в протокол
            свод = {}
            for ч in люди:
                к = ч['person'].lower().replace('.', '').replace(' ', '')
                с = свод.setdefault(к, ч)
                if len(ч.get('post') or '') > len(с.get('post') or ''):
                    с['post'] = ч['post']
                if ч.get('phone') and not с.get('phone'):
                    с['phone'] = ч['phone']
            for ч in свод.values():
                роль = EDB.EnrichDB._canon_role(ч.get('post') or '')
                out['людей'] += 1
                if роль in EDB.EnrichDB.TECH_ROLES:
                    out['техЛПР'] += 1
                    if len(out['примеры']) < 16:
                        out['примеры'].append(
                            {'инн': inn, 'фио': ч['person'],
                             'должность': ч.get('post'),
                             'в_комиссии': ч.get('in_commission'),
                             'ссылка': (ч.get('url') or '')[:80]})
                тел = (ч.get('phone') or '').strip()
                if тел and list(EC.phones_in(тел)):
                    out['телефонов'] += 1
                if ПРИМЕНИТЬ:
                    db.add_person(inn, ч['person'], post=ч.get('post') or '',
                                  phone=тел, source='закупочная комиссия',
                                  source_url=ч.get('url') or '')
                    if тел and list(EC.phones_in(тел)):
                        e.execute(
                            'INSERT OR IGNORE INTO phone_contacts(inn, phone,'
                            ' person, role, source, source_url, updated_at) '
                            'VALUES(?,?,?,?,?,?,datetime("now"))',
                            (inn, тел, ч['person'], роль or '',
                             'закупочная комиссия', ч.get('url') or ''))
            итог['людей'] = len(свод)
        except Exception as ex:  # noqa: BLE001
            итог['err'] = f'{type(ex).__name__}: {str(ex)[:70]}'
            out['ошибок'] += 1
        if ПРИМЕНИТЬ:
            e.commit()
        out['пройдено'] += 1
        ф.write(json.dumps(итог, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())
    ф.close()
    print(json.dumps(out, ensure_ascii=False, indent=1)[:6000])
    print(json.dumps({k: v for k, v in out.items() if k != 'примеры'},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
