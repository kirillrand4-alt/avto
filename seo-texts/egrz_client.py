# -*- coding: utf-8 -*-
"""Клиент ЕГРЗ - единый реестр заключений экспертизы проектной документации.

ЗАЧЕМ. Это самый ранний ГОТОВЫЙ сигнал в цепочке: проектная документация проходит
экспертизу ДО того, как объявлена закупка оборудования. Если в заключении стоит
"компрессорная станция" или "воздухоразделительная установка", у предприятия есть
проект и есть застройщик с ИНН, а закупки ещё нет. Это и есть "от события на
ранней стадии".

ЭНДПОИНТ. https://open-api.egrz.ru/api/PublicRegistrationBook - OData v4, без ключа
и без авторизации. На 16.09.2026 в реестре 596903 записи, отвечает 200.

ТРИ ЛОВУШКИ, каждая проверена прямым замером (не догадки):

1. TLS. egrz.ru требует legacy renegotiation. Лечится конфигом OpenSSL, НЕ
   отключением проверки сертификата. Переменная OPENSSL_CONF читается OpenSSL при
   инициализации библиотеки, то есть ДО того как питон доберётся до нашего кода,
   поэтому os.environ[...] в начале скрипта уже опаздывает. Решение - скрипт
   перезапускает сам себя (os.execve) с нужной переменной. Смотри podgotovit_tls().

2. contains() РЕГИСТРОЗАВИСИМ. Прямой замер по слову "компрессорная":
       строчными      'компрессорная'   -> 208
       с заглавной    'Компрессорная'   ->  65
       прописными     'КОМПРЕССОРНАЯ'   ->   1
       tolower(поле)  'компрессорная'   -> 274   (208+65+1, сходится точно)
   То есть наивный поиск строчными молча теряет четверть находок и при этом
   выглядит как нормально сработавший фильтр. Везде используем tolower(поле).

3. $top больше 100 - это HTTP 400, а не усечение. 500/1000/5000 проверены, все 400.
   Поэтому страница 100 записей и никак иначе.

КОНТРОЛЬ. Любой замер сопровождается запросом с заведомо выдуманным словом
"щварцкопфер": он обязан дать ровно 0. Если даёт не 0 - фильтр не фильтрует,
и всем остальным числам этого прогона верить нельзя. Функция kontrol_filtra().

ПОЛЯ ЗАПИСИ (42 штуки, главные):
    ExpertiseNumber, ExpertiseConclusionDate, ExpertiseResultType, ExpertiseType
    ExpertiseObjectName, ExpertiseObjectAddress, ExpertiseObjectNameAndAddress
    SubjectRf, SubjectRfCode                 - регион прямо в записи
    FunctionalPurpose, WorkType              - назначение и вид работ
    DeveloperOrganizationInfo                - ЗАСТРОЙЩИК, строкой, с ИНН/ОГРН/КПП/адресом
    TechnicalCustomerOrganizationInfo        - технический заказчик
    DeveloperAndTechnicalCustomerOrganizationInfo - когда это одно лицо
    PlannerOrganizationInfo                  - проектировщик
    ExpertiseOrganizatioINN                  - ИНН экспертной организации (не наш клиент)

ИНН застройщика лежит не отдельным полем, а внутри строки вида
    НАЗВАНИЕ (ОГРН: 1053458081621, ИНН: 3421002834, КПП: 342101001, МЕСТО ...)
Разбирает razobrat_organizaciyu(). ФИО в реестре нет вовсе - это источник
предприятий и ИНН, а не людей; человека добываем уже по ИНН другими путями.

Использование:
    python3 egrz_client.py proba-slov              - отдача каждого слова по одному
    python3 egrz_client.py schet --slovo компрессорная
    python3 egrz_client.py vygruzka --slova-fayl slova.txt --s-daty 2025-09-16 \
        --tolko-polozhitelnye --vyhod /tmp/egrz.jsonl
    python3 egrz_client.py polya                   - показать поля одной записи
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

BAZA = 'https://open-api.egrz.ru/api/PublicRegistrationBook'

# Слово, которого в реестре быть не может. Служит контролем: если по нему нашлось
# хоть что-то - фильтр не работает и числа прогона недействительны.
SLOVO_KONTROL = 'щварцкопфер'

KONFIG_TLS = """openssl_conf = default_conf
[default_conf]
ssl_conf = ssl_sect
[ssl_sect]
system_default = system_default_sect
[system_default_sect]
Options = UnsafeLegacyRenegotiation
CipherString = DEFAULT:@SECLEVEL=0
"""


def podgotovit_tls():
    """Перезапустить процесс с OPENSSL_CONF, если он ещё не выставлен.

    OpenSSL читает эту переменную один раз, при загрузке библиотеки, то есть
    раньше нашего кода. Менять os.environ в работающем процессе бесполезно -
    ssl уже поднят со старым конфигом. Единственный честный способ - заменить
    процесс на себя же с правильным окружением. Отключение проверки сертификата
    (ssl._create_unverified_context) решило бы симптом и сломало бы безопасность,
    поэтому так не делаем.
    """
    if os.environ.get('EGRZ_TLS_GOTOV') == '1':
        return
    put = os.environ.get('OPENSSL_CONF') or ''
    if not (put and os.path.exists(put) and 'UnsafeLegacyRenegotiation' in open(put).read()):
        katalog = os.environ.get('TMPDIR') or '/tmp'
        put = os.path.join(katalog, 'egrz_ossl.cnf')
        with open(put, 'w') as f:
            f.write(KONFIG_TLS)
    sreda = dict(os.environ)
    sreda['OPENSSL_CONF'] = put
    sreda['EGRZ_TLS_GOTOV'] = '1'
    os.execve(sys.executable, [sys.executable] + sys.argv, sreda)


def zapros(parametry, popytok=4, tishe=False):
    """Один запрос к OData. Возвращает (kod_http, razobrannyy_json_ili_None, tekst).

    Код ответа возвращается ВСЕГДА, в том числе для 4xx/5xx: хост, ответивший
    400 или 429, достигнут - это ответ, а не недоступность. Молчанием считается
    только обрыв связи, и он тоже возвращается кодом 0 с текстом ошибки.
    """
    url = BAZA + '?' + urllib.parse.urlencode(parametry)
    posledniy = (0, None, 'попыток не было')
    for nomer in range(1, popytok + 1):
        try:
            zapr = urllib.request.Request(url, headers={
                'Accept': 'application/json',
                'User-Agent': 'python-urllib/3 (egrz_client)',
            })
            with urllib.request.urlopen(zapr, timeout=90) as otvet:
                kod = otvet.getcode()
                telo = otvet.read().decode('utf-8', 'replace')
            try:
                return kod, json.loads(telo), telo
            except ValueError:
                posledniy = (kod, None, 'ответ не разобрался как JSON: ' + telo[:300])
        except urllib.error.HTTPError as e:
            telo = e.read().decode('utf-8', 'replace')
            # 400 обычно означает кривой фильтр и повтором не лечится
            if e.code in (400, 404, 501):
                return e.code, None, telo[:500]
            posledniy = (e.code, None, telo[:300])
        except Exception as e:
            posledniy = (0, None, '%s: %s' % (type(e).__name__, e))
        if nomer < popytok:
            pauza = min(30, 2 ** nomer)
            if not tishe:
                print('   повтор %d/%d через %d с (было: %s)'
                      % (nomer, popytok, pauza, str(posledniy[2])[:120]), file=sys.stderr)
            time.sleep(pauza)
    return posledniy


def schet(filtr, tishe=False):
    """Сколько записей подходит под фильтр. Возвращает (chislo_ili_None, kod_http)."""
    par = {'$top': '0', '$count': 'true'}
    if filtr:
        par['$filter'] = filtr
    kod, dan, tekst = zapros(par, tishe=tishe)
    if dan is None:
        if not tishe:
            print('   ОТВЕТ %s, счёт не получен: %s' % (kod, str(tekst)[:200]), file=sys.stderr)
        return None, kod
    return dan.get('@odata.count'), kod


def uslovie_slova(slovo, pole='ExpertiseObjectName'):
    """Условие OData на вхождение слова. Всегда через tolower - см. ловушку 2."""
    bezopasno = slovo.lower().replace("'", "''")
    return "contains(tolower(%s),'%s')" % (pole, bezopasno)


def sobrat_filtr(slova=None, s_daty=None, po_datu=None, tolko_polozhitelnye=False,
                 region=None, pole='ExpertiseObjectName'):
    """Склеить условия в один $filter. Слова объединяются через or, остальное через and."""
    chasti = []
    if slova:
        chasti.append('(' + ' or '.join(uslovie_slova(s, pole) for s in slova) + ')')
    if s_daty:
        chasti.append('ExpertiseConclusionDate ge %sT00:00:00Z' % s_daty)
    if po_datu:
        chasti.append('ExpertiseConclusionDate le %sT23:59:59Z' % po_datu)
    if tolko_polozhitelnye:
        chasti.append("ExpertiseResultType eq 'Положительное заключение'")
    if region:
        chasti.append(uslovie_slova(region, 'SubjectRf'))
    return ' and '.join(chasti)


def kontrol_filtra(prochie_usloviya=None):
    """КОНТРОЛЬ. Запрос с заведомо выдуманным словом обязан дать ровно 0.

    Ноль надо доказывать так же тщательно, как находку: если фильтр по мусорному
    слову возвращает непустой счёт, значит параметр $filter сервером игнорируется
    (или мы его неправильно передаём), и любые "находки" этого прогона - на самом
    деле просто первые записи реестра. Возвращает True, если прибор исправен.
    """
    filtr = uslovie_slova(SLOVO_KONTROL)
    if prochie_usloviya:
        filtr = filtr + ' and ' + prochie_usloviya
    chislo, kod = schet(filtr)
    ok = (chislo == 0)
    print('КОНТРОЛЬ фильтра: слово %r -> count=%s, http=%s -> %s'
          % (SLOVO_KONTROL, chislo, kod, 'прибор исправен' if ok else 'ПРИБОР ВРЁТ'))
    if not ok:
        print('   фильтр не фильтрует, числам этого прогона верить нельзя', file=sys.stderr)
    return ok


def kontrol_tolower():
    """КОНТРОЛЬ регистра: сумма трёх написаний обязана сойтись с tolower().

    Если не сходится, значит либо tolower на сервере работает не так, как мы
    думаем, либо написаний больше трёх - в обоих случаях надо разбираться, а не
    брать число на веру.
    """
    slovo = 'компрессорная'
    n_niz, _ = schet("contains(ExpertiseObjectName,'%s')" % slovo, tishe=True)
    n_zagl, _ = schet("contains(ExpertiseObjectName,'%s')" % slovo.capitalize(), tishe=True)
    n_verh, _ = schet("contains(ExpertiseObjectName,'%s')" % slovo.upper(), tishe=True)
    n_tl, _ = schet(uslovie_slova(slovo), tishe=True)
    summa = sum(x for x in (n_niz, n_zagl, n_verh) if x is not None)
    ok = (summa == n_tl)
    print('КОНТРОЛЬ регистра: строчные=%s + Заглавная=%s + ПРОПИСНЫЕ=%s = %s, tolower=%s -> %s'
          % (n_niz, n_zagl, n_verh, summa, n_tl, 'сходится' if ok else 'НЕ СХОДИТСЯ'))
    return ok


def razobrat_organizaciyu(stroka):
    """Вытащить название, ИНН, ОГРН, КПП и адрес из строки организации.

    Формат в реестре:
        НАЗВАНИЕ (ОГРН: 1053458081621, ИНН: 3421002834, КПП: 342101001,
                  МЕСТО НАХОЖДЕНИЯ и АДРЕС: ...)
    Часть записей идёт без скобочного хвоста - тогда есть только название, и это
    не ошибка разбора, а реальное отсутствие реквизитов в реестре.
    """
    if not stroka or not isinstance(stroka, str):
        return None
    itog = {'syroe': stroka}
    m = re.search(r'ИНН:\s*(\d{10}|\d{12})', stroka)
    itog['inn'] = m.group(1) if m else ''
    m = re.search(r'ОГРН:\s*(\d{13}|\d{15})', stroka)
    itog['ogrn'] = m.group(1) if m else ''
    m = re.search(r'КПП:\s*(\d{9})', stroka)
    itog['kpp'] = m.group(1) if m else ''
    m = re.search(r'МЕСТО НАХОЖДЕНИЯ и АДРЕС:\s*(.+?)\s*\)\s*$', stroka, re.S)
    itog['adres'] = m.group(1).strip() if m else ''
    nazvanie = re.split(r'\s*\((?:ОГРН|ИНН)[:\s]', stroka)[0].strip()
    itog['nazvanie'] = nazvanie
    return itog


# Поля, которых хватает для сшивки с нашей базой по ИНН. Полная запись весит
# 12 КБ, эта проекция - 5 КБ, на 70 тысячах записей разница 350 МБ против 150.
POLYA_COMPACT = ('Key,ExpertiseNumber,ExpertiseConclusionDate,ExpertiseResultType,'
                 'ExpertiseObjectName,ExpertiseObjectAddress,SubjectRf,FunctionalPurpose,'
                 'WorkType,DeveloperOrganizationInfo,TechnicalCustomerOrganizationInfo,'
                 'DeveloperAndTechnicalCustomerOrganizationInfo,PlannerOrganizationInfo')


def vygruzka(filtr, predel=None, vyhod=None, shag=100, select=None):
    """Постраничная выгрузка через $skip/$top. Возвращает список записей.

    Сортировка по Key обязательна: без устойчивого порядка страницы могут
    перекрываться и терять записи. $top больше 100 - это HTTP 400, см. ловушку 3.
    """
    vsego, kod = schet(filtr)
    print('ВЫГРУЗКА: http=%s, подходит записей=%s' % (kod, vsego), flush=True)
    if vsego is None:
        return []
    nado = vsego if predel is None else min(vsego, predel)
    sobrano = []
    f = open(vyhod, 'w', encoding='utf-8') if vyhod else None
    skip = 0
    try:
        while skip < nado:
            par = {'$top': str(min(shag, nado - skip)), '$skip': str(skip),
                   '$orderby': 'Key'}
            if select:
                par['$select'] = select
            if filtr:
                par['$filter'] = filtr
            kod, dan, tekst = zapros(par)
            if dan is None:
                print('   страница skip=%d НЕ ПОЛУЧЕНА, http=%s: %s'
                      % (skip, kod, str(tekst)[:200]), file=sys.stderr)
                break
            zapisi = dan.get('value') or []
            if not zapisi:
                print('   страница skip=%d пуста, http=%s - выгрузка окончена' % (skip, kod))
                break
            for z in zapisi:
                sobrano.append(z)
                if f:
                    f.write(json.dumps(z, ensure_ascii=False) + '\n')
            skip += len(zapisi)
            if (skip // shag) % 20 == 0 or skip >= nado:
                print('   skip=%-7d http=%s получено=%-4d всего=%d/%d'
                      % (skip - len(zapisi), kod, len(zapisi), len(sobrano), nado), flush=True)
    finally:
        if f:
            f.close()
    print('ВЫГРУЗКА окончена: записей=%d%s'
          % (len(sobrano), (', файл ' + vyhod) if vyhod else ''), flush=True)
    return sobrano


SLOVA_PO_UMOLCHANIYU = [
    'компрессорная', 'компрессорной', 'компрессор',
    'воздухоразделительная', 'азотная станция', 'кислородная станция',
    'котельная', 'очистные сооружения',
    'реконструкция', 'техническое перевооружение',
    'завод', 'комбинат', 'цех',
]


def proba_slov(slova, obshchie=None, pole='ExpertiseObjectName'):
    """Отдача каждого слова ПО ОДНОМУ. Слово с нулём в рабочий список не идёт.

    Проверять слова поодиночке, а не пачкой - единственный способ увидеть, что
    какое-то из них не даёт ничего: в объединении через or нулевое слово
    невидимо, оно просто ничего не добавляет к чужой отдаче.
    """
    print('%-28s %10s %10s  %s' % ('слово', 'всего', 'с условием', 'http'))
    itogi = []
    for s in slova:
        f1 = uslovie_slova(s, pole)
        n1, k1 = schet(f1, tishe=True)
        if obshchie:
            n2, k2 = schet(f1 + ' and ' + obshchie, tishe=True)
        else:
            n2, k2 = n1, k1
        print('%-28s %10s %10s  %s/%s%s'
              % (s, n1, n2, k1, k2, '   <- НОЛЬ, в список не идёт' if not n1 else ''))
        itogi.append({'slovo': s, 'vsego': n1, 's_usloviem': n2, 'http': k1})
    return itogi


def glavnaya():
    razbor = argparse.ArgumentParser(description='Клиент ЕГРЗ')
    razbor.add_argument('rezhim', choices=['polya', 'schet', 'proba-slov', 'vygruzka', 'kontrol'])
    razbor.add_argument('--slovo', action='append', default=[])
    razbor.add_argument('--slova-fayl')
    razbor.add_argument('--s-daty')
    razbor.add_argument('--po-datu')
    razbor.add_argument('--region')
    razbor.add_argument('--tolko-polozhitelnye', action='store_true')
    razbor.add_argument('--pole', default='ExpertiseObjectName')
    razbor.add_argument('--predel', type=int)
    razbor.add_argument('--vyhod')
    razbor.add_argument('--compact', action='store_true',
                        help='тянуть только поля, нужные для сшивки по ИНН')
    a = razbor.parse_args()

    slova = list(a.slovo)
    if a.slova_fayl:
        with open(a.slova_fayl, encoding='utf-8') as f:
            slova += [s.strip() for s in f if s.strip() and not s.startswith('#')]

    if a.rezhim == 'polya':
        kod, dan, tekst = zapros({'$top': '1', '$count': 'true'})
        print('http=%s, всего в реестре=%s' % (kod, (dan or {}).get('@odata.count')))
        if dan:
            z = dan['value'][0]
            print('полей в записи: %d' % len(z))
            for k, v in z.items():
                print('  %-46s %s' % (k, json.dumps(v, ensure_ascii=False)[:150]))
        return

    if a.rezhim == 'kontrol':
        ok1 = kontrol_filtra()
        ok2 = kontrol_tolower()
        sys.exit(0 if (ok1 and ok2) else 1)

    obshchie = sobrat_filtr(s_daty=a.s_daty, po_datu=a.po_datu,
                            tolko_polozhitelnye=a.tolko_polozhitelnye, region=a.region)

    if not kontrol_filtra(obshchie or None):
        sys.exit('контроль не пройден, прогон остановлен')

    if a.rezhim == 'proba-slov':
        proba_slov(slova or SLOVA_PO_UMOLCHANIYU, obshchie or None, a.pole)
        return

    filtr = sobrat_filtr(slova=slova or None, s_daty=a.s_daty, po_datu=a.po_datu,
                         tolko_polozhitelnye=a.tolko_polozhitelnye, region=a.region,
                         pole=a.pole)
    print('фильтр: %s' % filtr)
    if a.rezhim == 'schet':
        n, k = schet(filtr)
        print('count=%s http=%s' % (n, k))
    else:
        vygruzka(filtr, predel=a.predel, vyhod=a.vyhod,
                 select=POLYA_COMPACT if a.compact else None)


if __name__ == '__main__':
    podgotovit_tls()
    glavnaya()
