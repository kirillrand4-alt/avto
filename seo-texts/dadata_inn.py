# -*- coding: utf-8 -*-
"""Разрешение названий организаций в ИНН через справочник ЕГРЮЛ DaData.

Зачем. Отфильтрованная выдача Сбербанк-АСТ отдаёт `OrgName`, но **не отдаёт `OrgInn`** —
у поиска через Elasticsearch другой набор полей, чем у списка по умолчанию. Поэтому 3 774
организатора лежат названиями, а пересечь их с нашими 246 предприятиями нельзя: сличение
строк подводило 30.07.2026 трижды («Магнитогорский металлургический комбинат» слипся с
«Комбинатом хлебопродуктов» по слову «комбинат», потом с «Магнитогорским Гипромезом» по
названию города).

Справочник решает это правильно: он возвращает **идентификатор**, а не пару строк.
Открывается прямо из песочницы, токен лежит в ключнице раннера, лимит 10 000 запросов в день.
Бонусом отдаёт руководителя с должностью и статус в ЕГРЮЛ.

Заслоны, каждый по конкретной ошибке:
- **профсоюзы и садоводческие товарищества отсекаются до выбора**: по запросу
  «Новокуйбышевский НПЗ» справочник первым отдаёт профсоюз с именем завода внутри, и
  совпадение выглядит идеальным;
- **ликвидированные помечаются, а не выбрасываются молча**: ВТЗ, ЕВРАЗ ЗСМК, ФКП «БОЗ» и
  АО «СТЗ» уже нашлись мёртвыми, и это тоже факт, который надо видеть;
- **при нескольких кандидатах это видно в колонке `kandidatov`**, и такие строки нельзя
  считать разрешёнными. Берётся первый — но это не выбор, а заготовка для проверки.

  **Насколько это существенно, замерено сразу:** на первых 60 названиях кандидатов больше
  одного у **26**. Причина в том, что выдача Сбербанк-АСТ **не даёт региона**, а «АО
  «Водоканал»» или «АО «ЧМЗ»» в России не по одному. Развести их нечем, и строку с
  `kandidatov > 1` надо считать **гипотезой**, а не привязкой. Для нашей задачи это терпимо
  ровно в одном случае: если ИНН всё равно попадает в наш список 246 предприятий — тогда
  совпадение подтверждено с другой стороны.

Использование:
    python3 dadata_inn.py <names.txt> <out.csv> [--threads 6] [--limit 4000]
"""
import csv
import json
import os
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

URL = 'https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party'
# ОКВЭД и формы, которые почти всегда означают «не то предприятие, а его спутник»
SPUTNIK = re.compile(r'профсоюз|профессиональн\w+ союз|садовод|дачн|гаражн|товарищество '
                     r'собственник|фонд|ассоциац|некоммерческ\w+ партнер', re.I)


def token():
    t = os.environ.get('DADATA_TOKEN')
    if t:
        return t.strip()
    for p in ('rs.env', 'runner-secrets.env',
              os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server',
                           'runner-secrets.env')):
        if os.path.exists(p):
            for line in open(p, encoding='utf-8', errors='replace'):
                if line.startswith('DADATA_TOKEN'):
                    return line.split('=', 1)[1].strip().strip('"').strip()
    sys.exit('нет DADATA_TOKEN ни в окружении, ни в rs.env')


TOK = None


def sprosit(nazvanie):
    body = json.dumps({'query': nazvanie[:250], 'count': 5}, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(URL, data=body, headers={
        'Content-Type': 'application/json', 'Accept': 'application/json',
        'Authorization': 'Token ' + TOK})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))


def razobrat(nazvanie, otvet):
    sug = otvet.get('suggestions') or []
    godnye = [s for s in sug if not SPUTNIK.search(s.get('value') or '')]
    otseyano = len(sug) - len(godnye)
    if not godnye:
        return {'nazvanie': nazvanie, 'inn': '', 'pochemu': 'кандидатов нет'
                if not sug else f'все {len(sug)} — спутники (профсоюз, фонд и т. п.)'}
    s = godnye[0]
    d = s.get('data') or {}
    po_inn = bool(re.fullmatch(r'\d{10}|\d{12}', (nazvanie or '').strip()))
    m = d.get('management') or {}
    st = (d.get('state') or {}).get('status') or ''
    return {'nazvanie': nazvanie,
            'inn': d.get('inn') or '',
            'nazvanie_egrul': s.get('value') or '',
            'kpp': d.get('kpp') or '',
            'region': ((d.get('address') or {}).get('data') or {}).get('region_with_type') or '',
            'okved': d.get('okved') or '',
            'status': st,
            'rukovoditel': m.get('name') or '',
            'dolzhnost': m.get('post') or '',
            # Запрос ПО ИНН — привязка точная, сколько бы подсказок ни вернул справочник.
            # DaData на ИНН отдаёт головную организацию и её филиалы, и прежде это писалось как
            # «несколько кандидатов», из-за чего строку отбраковывал svod_tri_sostoyaniya как
            # неоднозначную. Для запроса по названию число кандидатов остаётся сигналом недоверия.
            'kandidatov': 1 if po_inn else len(godnye),
            'pochemu': ('запрос по ИНН, привязка точная' if po_inn else
                        (f'отсеяно спутников: {otseyano}; ' if otseyano else '')
                        + ('несколько кандидатов, взят первый' if len(godnye) > 1
                           else 'один кандидат'))}


def main():
    global TOK
    if len(sys.argv) < 3:
        sys.exit('usage: dadata_inn.py <names.txt> <out.csv> [--threads N] [--limit N]')
    src, out = sys.argv[1], sys.argv[2]
    threads = int(sys.argv[sys.argv.index('--threads') + 1]) if '--threads' in sys.argv else 6
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else 9000
    TOK = token()

    imena = [l.strip() for l in open(src, encoding='utf-8') if l.strip()][:limit]
    print(f'названий: {len(imena)}, потоков {threads}', file=sys.stderr)

    cols = ['nazvanie', 'inn', 'nazvanie_egrul', 'kpp', 'region', 'okved', 'status',
            'rukovoditel', 'dolzhnost', 'kandidatov', 'pochemu']
    f = open(out, 'w', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
    w.writeheader()
    lock = threading.Lock()
    schet = {'ok': 0, 'net': 0, 'err': 0}

    def odno(nazvanie):
        for popytka in range(3):
            try:
                return razobrat(nazvanie, sprosit(nazvanie))
            except Exception as e:  # noqa: BLE001
                if popytka == 2:
                    return {'nazvanie': nazvanie, 'inn': '',
                            'pochemu': f'ОШИБКА {type(e).__name__}: {str(e)[:60]}'}
                time.sleep(1.5 * (popytka + 1))

    with ThreadPoolExecutor(max_workers=threads) as pool:
        for i, r in enumerate(pool.map(odno, imena), 1):
            with lock:
                w.writerow(r)
                if r.get('inn'):
                    schet['ok'] += 1
                elif 'ОШИБКА' in (r.get('pochemu') or ''):
                    schet['err'] += 1
                else:
                    schet['net'] += 1
                if i % 500 == 0:
                    f.flush()
                    print(f'  {i}/{len(imena)}: с ИНН {schet["ok"]}, без {schet["net"]}, '
                          f'ошибок {schet["err"]}', file=sys.stderr)
    f.close()
    print(f'готово: с ИНН {schet["ok"]}, без ИНН {schet["net"]}, ошибок {schet["err"]} → {out}',
          file=sys.stderr)


if __name__ == '__main__':
    main()
