# -*- coding: utf-8 -*-
"""АДВЕРСАРИАЛЬНАЯ проверка тезиса «протоколы комиссии в ЕИС не выкладывают».

Подозрение к коду, а не к источнику: eis_documents берёт ПЕРВУЮ ссылку со
словом documents (вкладка «Документы» извещения) и читает только filestore с
неё. Протоколы в ЕИС лежат на ДРУГОЙ вкладке — «Результаты определения
поставщика» (44-ФЗ) и «Протоколы» (223-ФЗ). Если это так, боевой код физически
не может их увидеть, и «протоколов нет» — вывод об инструменте, а не о ЕИС.

Печатаем ВСЕ вкладки карточки с их подписями, отдельно всё, где встречается
protocol/протокол/result, и что лежит на этих вкладках.

Запуск: python _ops_check_eis_proto.py ИНН [ИНН]
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

_КОМ = re.compile(r'председател\w*\s+комисси|член\w*\s+комисси|секретар\w*\s+комисси'
                  r'|состав\w*\s+комисси|протокол\w*\s+заседани|заседани\w*\s+комисси',
                  re.I)
_ФИО = re.compile(r'[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.'
                  r'|[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+')


def main():
    буф = []

    def P(s):
        буф.append(str(s))

    инны = [a for a in sys.argv[1:] if a.isdigit()] or ['3801098402', '7424024375']
    итог = {'карточек': 0, 'вкладок_documents': 0, 'вкладок_протокол': 0,
            'файлов_боевых': 0, 'файлов_на_протокольных': 0,
            'протоколов_прочитано': 0, 'с_составом_комиссии': 0, 'фио_найдено': 0}
    прото_ссылки = []
    for inn in инны[:2]:
        z = EC.find_zakupki_contacts(inn, max_cards=4)
        карты = ((z or {}).get('cards') or [])
        P(f'=== ИНН {inn}: rss={(z or {}).get("rss_items")} карточек={len(карты)} '
          f'{(z or {}).get("error") or ""}')
        for c in карты[:3]:
            u = c.get('url') or ''
            итог['карточек'] += 1
            try:
                h = EC._eis_get(u)
            except Exception as ex:  # noqa: BLE001
                P(f'  карточка не открылась: {type(ex).__name__}')
                continue
            P(f'  КАРТОЧКА {u[-70:]} html={len(h)}')
            # ВСЕ вкладки навигации с подписями
            вкладки = []
            for m in re.finditer(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', h, re.S):
                href, подпись = m.group(1), re.sub(
                    r'\s+', ' ', re.sub(r'<[^>]+>', ' ', m.group(2))).strip()
                if '/epz/order/notice' in href or 'protocol' in href.lower() \
                        or 'supplier-results' in href.lower():
                    if подпись and (href, подпись) not in вкладки:
                        вкладки.append((href, подпись))
            P('    вкладки: ' + json.dumps(
                [п for _h, п in вкладки][:12], ensure_ascii=False))
            док = [x for x in вкладки if 'documents' in x[0]]
            прот = [x for x in вкладки
                    if re.search(r'protocol|результат|supplier-results', x[0] + x[1],
                                 re.I)]
            итог['вкладок_documents'] += len(док)
            итог['вкладок_протокол'] += len(прот)
            for hr, п in прот[:3]:
                P(f'    ПРОТОКОЛЬНАЯ ВКЛАДКА: «{п}» -> {hr[:110]}')
                full = hr.replace('&amp;', '&')
                if full.startswith('/'):
                    full = 'https://zakupki.gov.ru' + full
                прото_ссылки.append(full)
            # что видит БОЕВОЙ eis_documents
            бф = EC.eis_documents(u)
            итог['файлов_боевых'] += len(бф)
            P(f'    боевой eis_documents вернул файлов={len(бф)}: '
              + json.dumps([n[:45] for n, _ in бф][:6], ensure_ascii=False))

    # открываем протокольные вкладки, которых боевой код не касается
    P('=== ПРОТОКОЛЬНЫЕ ВКЛАДКИ ===')
    for full in прото_ссылки[:4]:
        try:
            hp = EC._eis_get(full)
        except Exception as ex:  # noqa: BLE001
            P(f'  {full[-60:]} не открылась: {type(ex).__name__}')
            continue
        файлы = []
        for m2 in re.finditer(
                r'<a\b[^>]*href="(https://zakupki\.gov\.ru/[^"]*filestore[^"]*)"'
                r'[^>]*>(.*?)</a>', hp, re.S):
            имя = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', m2.group(2))).strip()
            файлы.append((имя[:70], m2.group(1).replace('&amp;', '&')))
        txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', hp))
        P(f'  {full[-75:]} html={len(hp)} файлов={len(файлы)}')
        P('    имена: ' + json.dumps([n for n, _ in файлы][:8], ensure_ascii=False))
        м = _КОМ.search(txt)
        if м:
            i = м.start()
            P('    НА САМОЙ СТРАНИЦЕ> ' + txt[max(0, i - 200):i + 400])
        итог['файлов_на_протокольных'] += len(файлы)
        for имя, ссылка in файлы[:3]:
            t = EC.doc_text(ссылка)
            итог['протоколов_прочитано'] += 1
            P(f'    ФАЙЛ «{имя}» символов={len(t or "")}')
            if not t:
                continue
            найд = _КОМ.findall(t)
            if найд:
                итог['с_составом_комиссии'] += 1
                m3 = _КОМ.search(t)
                P('      КОМИССИЯ> ' + re.sub(
                    r'\s+', ' ', t[max(0, m3.start() - 250):m3.start() + 700]))
                фио = sorted(set(_ФИО.findall(t)))
                итог['фио_найдено'] += len(фио)
                P(f'      фио_в_документе={len(фио)} {фио[:10]}')
            else:
                P('      начало> ' + re.sub(r'\s+', ' ', t)[:200])
    print('\n'.join(буф)[-11500:])
    print('ИТОГ ' + json.dumps(итог, ensure_ascii=False))


if __name__ == '__main__':
    main()
