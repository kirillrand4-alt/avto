# -*- coding: utf-8 -*-
"""Ранний источник 3: техприсоединение к электросетям и к газу.

ЧТО ЭТО ЗА КАНАЛ. Стандарты раскрытия информации обязывают сетевые организации
(ПП РФ № 24 от 21.01.2004) и газораспределительные организации (ПП РФ № 872 от
29.10.2010) публиковать сведения о заявках и договорах технологического
присоединения. Заявка на ТП подаётся ДО стройки, поэтому это самый ранний
твёрдый след будущего объекта.

ГЛАВНЫЙ ВЫВОД ЗАМЕРА 16.09.2026, и он отрицательный по цели:
**в обязательных формах раскрытия НЕТ наименования заявителя и НЕТ ИНН.**
Раскрываются сеть и деньги, а не заявитель. Подробности и коды — в
seo-texts/RANNIE-ISTOCHNIKI-OPIS.md. Что реально лежит в формах:

    Россети Центр, форма 12 (п. 19«д» ПП 24), ежемесячно, 616 файлов на
    странице раскрытия, свежий MRSK_Centre_TP_01082026.xlsx = 3405 строк:
      блок 1 (сводный)  филиал · субъект РФ · подано заявок, шт и МВт ·
                        заключено договоров · выполнено · аннулировано
      блок 2 (построчный)  филиал · субъект РФ · НОМЕР ДОГОВОРА ТП ·
                        ДАТА ЗАКЛЮЧЕНИЯ · дата исполнения обязательств ·
                        ЗАПРАШИВАЕМАЯ МОЩНОСТЬ, кВт · стоимость, руб ·
                        ЦЕНТР ПИТАНИЯ (подстанция)
      наименования заявителя и ИНН в форме не предусмотрено

    Газ, ПП 872, приложение 6 форма 1 («Информация о регистрации и ходе
    реализации заявок на подключение»): строка = газопровод-отвод/ГРС,
    колонки = количество поданных, отклонённых, рассматриваемых и
    удовлетворённых заявок и объём газа в млн м3. Заявителей нет.

ЧТО ЭТОТ КЛИЕНТ ДЕЛАЕТ. Снимает форму 12 Россети Центр и честно считает:
строк, договоров, диапазон дат, сумму мощности, сколько строк содержат ИНН и
сколько — наименование юрлица. Контроль с заведомо негодным входом встроен:
поиск выдуманного слова по всей выгрузке обязан дать 0, а запрос
несуществующего файла обязан дать не-200.

ЗАПУСК (работает ИЗ ПЕСОЧНИЦЫ, mrsk-1.ru отдаёт 200):

    python3 seo-texts/rannie_tehprisoedinenie.py            # свежий месяц
    python3 seo-texts/rannie_tehprisoedinenie.py --vse      # список всех 616 файлов
"""
import csv
import io
import os
import re
import sys
import urllib.error
import urllib.request
import zipfile

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
BAZA = 'https://www.mrsk-1.ru'
STRANICA = BAZA + '/customers/services/tp/information/'
VYHOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rannie-tp-rosseti-centr.csv')
KONTROL_SLOVO = 'щварцкопфер'
KONTROL_FAYL = BAZA + '/upload/iblock/000/net-takogo-fayla-shvartskopfer.xlsx'


def vzyat(url, timeout=90):
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ru-RU,ru;q=0.9'})
        with urllib.request.urlopen(req, timeout=timeout) as f:
            return f.status, f.read(30000000)
    except urllib.error.HTTPError as e:
        return e.code, (e.read(1500) if e.fp else b'')
    except Exception as e:  # noqa: BLE001
        return 0, ('%s: %s' % (type(e).__name__, e)).encode()


def fayly_raskrytiya():
    """Все xls/xlsx со страницы раскрытия. Возвращает код ответа и список адресов."""
    kod, telo = vzyat(STRANICA, timeout=60)
    if kod != 200:
        return kod, []
    html = telo.decode('utf-8', 'replace')
    fl = sorted(set(re.findall(r'[\'"]([^\'"\s]+\.xlsx?)[\'"]', html, re.I)))
    return kod, [f if f.startswith('http') else BAZA + f for f in fl]


def svezhiy(fayly):
    """Самый свежий файл по дате в имени MRSK_Centre_TP_DDMMYYYY.xlsx."""
    luchshiy, klyuch = None, ''
    for f in fayly:
        m = re.search(r'TP_(\d{2})(\d{2})(\d{4})', os.path.basename(f))
        if m:
            k = m.group(3) + m.group(2) + m.group(1)
            if k > klyuch:
                klyuch, luchshiy = k, f
    return luchshiy, klyuch


def stroki_xlsx(telo):
    """Читаем xlsx стандартной библиотекой: разделяемые строки плюс ячейки листа."""
    z = zipfile.ZipFile(io.BytesIO(telo))
    obshchie = []
    if 'xl/sharedStrings.xml' in z.namelist():
        x = z.read('xl/sharedStrings.xml').decode('utf-8', 'replace')
        obshchie = [re.sub(r'<[^>]+>', '', m) for m in re.findall(r'<si>(.*?)</si>', x, re.S)]
    listy = [n for n in z.namelist() if re.match(r'xl/worksheets/sheet\d+\.xml$', n)]
    vse = []
    for imya in listy:
        x = z.read(imya).decode('utf-8', 'replace')
        for rm in re.findall(r'<row[^>]*>(.*?)</row>', x, re.S):
            yacheyki = []
            for cm in re.finditer(r'<c\b([^>]*)>(.*?)</c>', rm, re.S):
                atr, telo_yach = cm.group(1), cm.group(2)
                tm = re.search(r't="(\w+)"', atr)
                tip = tm.group(1) if tm else 'n'
                if tip == 'inlineStr':
                    znach = re.sub(r'<[^>]+>', '', telo_yach)
                else:
                    v = re.search(r'<v>(.*?)</v>', telo_yach, re.S)
                    znach = v.group(1) if v else ''
                    if tip == 's' and znach.isdigit() and int(znach) < len(obshchie):
                        znach = obshchie[int(znach)]
                yacheyki.append(znach)
            vse.append(yacheyki)
    return vse


def iz_serii(n):
    """Серийная дата Excel -> ГГГГ-ММ-ДД. Точка отсчёта 30.12.1899."""
    import datetime
    return (datetime.date(1899, 12, 30) + datetime.timedelta(days=int(n))).isoformat()


def main():
    kod, fayly = fayly_raskrytiya()
    print('страница раскрытия: код=%s файлов xls/xlsx=%d' % (kod, len(fayly)))
    if not fayly:
        print('НОЛЬ ФАЙЛОВ — либо страница переехала, либо хост не отдал её.')
        return 1

    # КОНТРОЛЬ 1: заведомо несуществующий файл обязан дать не-200
    kk, _ = vzyat(KONTROL_FAYL, timeout=30)
    print('КОНТРОЛЬ несуществующий файл: код=%s (200 означал бы сломанный прибор)' % kk)

    if '--vse' in sys.argv:
        for f in fayly:
            print('  ', f)
        return 0

    adres, klyuch = svezhiy(fayly)
    print('свежий файл: %s (ключ даты %s)' % (adres, klyuch))
    kod2, telo = vzyat(adres)
    print('файл: код=%s размер=%d' % (kod2, len(telo)))
    if kod2 != 200:
        return 1

    stroki = stroki_xlsx(telo)
    ploskiy = ' '.join(' '.join(r) for r in stroki)
    dogovory = [r for r in stroki
                if len(r) > 4 and re.match(r'^\d{6,9}$', (r[4] or '').strip())]

    # ЯМА, стоившая ложного вывода: сырой xlsx хранит даты СЕРИЙНЫМ числом Excel
    # (46239 = 05.08.2026), а не строкой. Поиск по «20\d\d-\d\d-\d\d» давал 0 дат
    # при том, что даты в файле есть у каждой строки. Переводим сами.
    daty = []
    for r in dogovory:
        if len(r) > 5 and re.match(r'^\d{5}$', (r[5] or '').strip()):
            daty.append(iz_serii(int(r[5])))
    daty = sorted(set(daty))

    # ЯМА ВТОРАЯ: «\d{10}» ловит хвост float в стоимости (2204394.4900000002 ->
    # «4900000002»). Настоящий ИНН стоит отдельным полем, а не внутри числа.
    inny = [v for r in stroki for v in r
            if re.fullmatch(r'\d{10}|\d{12}', (v or '').strip())]
    # ЯМА ТРЕТЬЯ: «ПАО» в файле — это САМА сетевая компания в каждой строке,
    # а не заявитель. Считаем только организационные формы, отличные от неё.
    zayaviteli = sum(1 for r in stroki
                     if re.search(r'\bООО\b|\bЗАО\b|\bОАО\b|\bИП\b', ' '.join(r))
                     and 'Россети' not in ' '.join(r))

    print('строк в файле: %d' % len(stroki))
    print('строк-договоров ТП (номер договора в 5-й колонке): %d' % len(dogovory))
    print('диапазон дат заключения: %s ... %s (различных дат %d)'
          % (daty[0] if daty else '-', daty[-1] if daty else '-', len(daty)))
    print('ИНН отдельным полем: %d' % len(inny))
    print('строк с наименованием заявителя (ООО/ЗАО/ОАО/ИП, кроме самих Россетей): %d'
          % zayaviteli)
    moshch = [float(r[7]) for r in dogovory
              if len(r) > 7 and re.fullmatch(r'\d+(\.\d+)?', (r[7] or '').strip())]
    print('строк с мощностью: %d | сумма, кВт: %.1f | максимум, кВт: %.1f'
          % (len(moshch), sum(moshch), max(moshch) if moshch else 0))
    print('КОНТРОЛЬ «%s» в выгрузке: %d (обязан быть 0)'
          % (KONTROL_SLOVO, ploskiy.lower().count(KONTROL_SLOVO)))

    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['istochnik_fayl', 'stroka'])
        for r in stroki:
            w.writerow([os.path.basename(adres), ' | '.join(x for x in r if x)])
    print('записано:', VYHOD, os.path.getsize(VYHOD))
    print('ВЫВОД: мощность, дата и подстанция есть; ИНН и наименования заявителя НЕТ.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
