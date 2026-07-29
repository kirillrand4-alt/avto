# -*- coding: utf-8 -*-
"""Пробить ОДНУ компанию всем арсеналом сразу (просьба владельца по конкретному ИНН).

Штатный конвейер идёт по спискам и пропускает компанию, помеченную конкурентом:
для рассылки это верно, но когда контакт по ней попросили лично, флаг мешать не
должен. Здесь он ИГНОРИРУЕТСЯ осознанно и только для указанного ИНН, сама
пометка в базе не трогается — она честная и нужна рассылке.

Что делаем по очереди, от дешёвого к дорогому:
  1. страницы руководства и контактов на сайте (обход + ссылки филиалов);
  2. те же страницы из поискового индекса — блок руководства часто не
     слинкован с главной;
  3. структурный разбор скачанного: ФИО + должность + телефон из ОДНОГО блока;
  4. переразметка ролей провайдером по собранному тексту;
  5. ЕИС: карточка организации в реестре и контакты из карточек закупок;
  6. hh: вакансии компании и контактное лицо, если оно опубликовано;
  7. checko: контакты карточки.
Всё скачанное кладём в кэш страниц, чтобы переразбор не стоил нового обхода.

Запуск: python _ops_one_company.py ИНН [--apply]
"""
import json
import re
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB          # noqa: E402
import enrich_contacts as EC     # noqa: E402

ПРИМЕНИТЬ = '--apply' in sys.argv
ИНН = next((a for a in sys.argv[1:] if a.isdigit()), '')

db = EDB.EnrichDB()
e = db.cx
out = {'инн': ИНН, 'шаги': {}, 'люди': [], 'телефоны': [], 'почты': [],
       'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой прогон (--apply)'}


def запиши_человека(фио, пост, тел, почта, источник, url):
    роль = EDB.EnrichDB._canon_role(пост or '')
    зап = {'фио': фио, 'должность': пост, 'роль': роль, 'тел': тел,
           'почта': почта, 'источник': источник, 'ссылка': (url or '')[:90]}
    if фио and not any(x['фио'] == фио and x['должность'] == пост
                       for x in out['люди']):
        out['люди'].append(зап)
    if ПРИМЕНИТЬ and фио:
        db.add_person(ИНН, фио, post=пост or '', phone=тел or '',
                      email=почта or '', source=источник, source_url=url or '')
    if тел:
        if not any(x['тел'] == тел for x in out['телефоны']):
            out['телефоны'].append({'тел': тел, 'кто': фио, 'роль': роль,
                                    'источник': источник,
                                    'ссылка': (url or '')[:90]})
        if ПРИМЕНИТЬ:
            e.execute('INSERT OR IGNORE INTO phone_contacts(inn, phone, person,'
                      ' role, source, source_url, updated_at) '
                      'VALUES(?,?,?,?,?,?,datetime("now"))',
                      (ИНН, тел, фио or '', роль or '', источник, url or ''))
    if почта:
        if not any(x['почта'] == почта for x in out['почты']):
            out['почты'].append({'почта': почта, 'кто': фио, 'роль': роль,
                                 'источник': источник})
        if ПРИМЕНИТЬ:
            db.add_email(ИНН, почта, role=роль or '', person=фио or '',
                         source=источник, source_url=url or '')


def main():
    if not ИНН:
        print(json.dumps({'ошибка': 'нужен ИНН'}, ensure_ascii=False))
        return
    c = e.execute('SELECT name, site FROM companies WHERE inn=?',
                  (ИНН,)).fetchone()
    имя = (c or ['', ''])[0] or ''
    дом = EC.site_domain((c or ['', ''])[1] or '')
    out['компания'], out['домен'] = имя, дом

    # --- 1-3. сайт: обход страниц руководства и контактов, структурный разбор
    if дом:
        адреса, гл = [], ''
        try:
            гл, _m, _mt = EC._fetch_site('http://' + дом)
        except Exception as ex:  # noqa: BLE001
            out['шаги']['главная'] = f'{type(ex).__name__}: {str(ex)[:60]}'
        # ссылки с главной, где в АДРЕСЕ есть подсказка про людей/контакты,
        # плюс страницы филиалов (у завода приёмная и главный инженер часто
        # сидят на странице площадки, а не головного)
        try:
            for u in re.findall(r'href="([^"#]+)"', гл or ''):
                н = u.lower()
                if not any(k in н for k in EC._STAFF_HINTS + ('contact', 'kontakt')):
                    continue
                if u.startswith('/'):
                    u = 'http://' + дом + u
                if EC.site_domain(u) == дом and u not in адреса:
                    адреса.append(u)
            адреса += [x for x in EC.branch_links(гл or '', дом)
                       if x not in адреса]
        except Exception:  # noqa: BLE001
            pass
        # 2. из поискового индекса
        try:
            из_поиска = EC.find_leadership_via_search({'name': имя}, дом,
                                                      max_urls=6)
        except Exception as ex:  # noqa: BLE001
            из_поиска = []
            out['шаги']['поиск'] = f'{type(ex).__name__}: {str(ex)[:60]}'
        план = list(dict.fromkeys(
            [f'http://{дом}/', f'http://{дом}/contacts/',
             f'http://{дом}/about/management/', f'http://{дом}/company/']
            + адреса + (из_поиска or [])))[:16]
        out['шаги']['страниц_в_плане'] = len(план)
        собрано, прочитано = [], 0
        for u in план:
            try:
                h, _m, mt = EC._fetch_site(u)
            except Exception:  # noqa: BLE001
                continue
            if not h or mt.get('captcha_type'):
                continue
            прочитано += 1
            собрано.append((u, h))
            for ч in EC.people_from_html(h, u):
                запиши_человека(ч.get('person'), ч.get('post'),
                                ч.get('phone'), ч.get('email'),
                                'сайт:руководство', u)
            time.sleep(0.4)
        out['шаги']['страниц_прочитано'] = прочитано
        # 4. переразметка ролей провайдером по собранному тексту
        if собрано:
            текст = EC._contact_cap('\n'.join(EC._текст(h) for _u, h in собрано))
            try:
                data, how = EC.extract_roles(текст, {'name': имя, 'inn': ИНН})
                out['шаги']['провайдер'] = how
                роли, _ = EC._norm_phone_roles(data.get('phone_roles')
                                               or data.get('phones'))
                for p in роли:
                    запиши_человека(p.get('person') or '',
                                    p.get('role') or p.get('dept') or '',
                                    p.get('phone'), '', 'сайт компании',
                                    собрано[0][0])
                for em in (data.get('emails') or []):
                    запиши_человека(em.get('person') or '', em.get('role') or '',
                                    '', (em.get('email') or '').lower(),
                                    'сайт компании', собрано[0][0])
            except Exception as ex:  # noqa: BLE001
                out['шаги']['провайдер'] = f'{type(ex).__name__}: {str(ex)[:60]}'
            try:
                EC._cache_pages(r'C:\seostat\drop\pagecache',
                                f'one_{ИНН}', дом, собрано, текст)
                out['шаги']['кэш'] = 'сложен'
            except Exception:  # noqa: BLE001
                pass

    # --- 5. ЕИС
    try:
        орг = EC.find_zakupki_org(ИНН)
        for ч in ((орг or {}).get('people') or []):
            запиши_человека(ч.get('person'), ч.get('post'), ч.get('phone'),
                            ч.get('email'), 'zakupki:реестр',
                            (орг or {}).get('url'))
        z = EC.find_zakupki_contacts(ИНН, max_cards=6)
        карточек = 0
        for карт in ((z or {}).get('cards') or []):
            карточек += 1
            for ч in (карт.get('people') or []):
                запиши_человека(ч.get('person'),
                                ч.get('post') or 'снабжение/закупки',
                                ч.get('phone'), ч.get('email'),
                                'zakupki:eis', карт.get('url'))
        out['шаги']['еис_карточек'] = карточек
    except Exception as ex:  # noqa: BLE001
        out['шаги']['еис'] = f'{type(ex).__name__}: {str(ex)[:60]}'

    # --- 6. hh
    try:
        h = EC.hh_lpr_contacts({'name': имя, 'inn': ИНН})
        out['шаги']['hh_вакансий'] = len((h or {}).get('vacancies') or [])
        out['вакансии'] = [(v.get('name') or '')[:70]
                           for v in ((h or {}).get('vacancies') or [])[:12]]
        for ч in ((h or {}).get('contacts') or []):
            запиши_человека(ч.get('person'), ч.get('post'), ч.get('phone'),
                            ч.get('email'), 'hh:вакансия', ч.get('url'))
    except Exception as ex:  # noqa: BLE001
        out['шаги']['hh'] = f'{type(ex).__name__}: {str(ex)[:60]}'

    if ПРИМЕНИТЬ:
        e.commit()
    out['итого'] = {'людей': len(out['люди']), 'телефонов': len(out['телефоны']),
                    'почт': len(out['почты']),
                    'техЛПР': sum(1 for x in out['люди']
                                  if x['роль'] in EDB.EnrichDB.TECH_ROLES)}
    print(json.dumps(out, ensure_ascii=False, indent=1)[:9000])
    print(json.dumps({'итого': out['итого'], 'шаги': out['шаги']},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
