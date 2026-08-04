# -*- coding: utf-8 -*-
"""Домен предприятия из корпоративной почты — потому что колонка `sayt` в p25.db пуста у всех.

ЗАМЕР, РАДИ КОТОРОГО ЭТО НАПИСАНО. Строгая приёмка P25 подтверждает человека, если страница —
сайт предприятия, страница про него на сайте холдинга, карточка закупки или документ
раскрытия. Из 261 найденного мной человека прошло 3. Причина оказалась не в людях: в
`p25.db` есть колонка `company.sayt`, и она **пуста у всех 491 предприятия**. То есть самый
сильный путь подтверждения — «страница на сайте предприятия» — не мог сработать НИ РАЗУ, и
низкий процент был свойством входа, а не выдачи.

ЧТО ЗДЕСЬ ДЕЛАЕТСЯ. Домен берётся из адреса корпоративной почты: `glavinzh@ugok.ru` → `ugok.ru`.
Публичные почтовики (mail.ru, yandex.ru, gmail.com…) отбрасываются — у них домен принадлежит
почтовику, а не предприятию, и принять его значит завтра засчитать подтверждением любую
страницу на mail.ru.

ЧЕСТНАЯ ГРАНИЦА. Домен почты — это СИЛЬНЫЙ, но не абсолютный признак: предприятие может
держать почту на домене холдинга (`ivanov@sibur.ru` у сотрудника ПОЛИЭФа). Для приёмки это
как раз годится — страница на сайте холдинга по ТЗ подтверждением считается. А вот обратное
неверно: домен почты не доказывает, что сайт с таким адресом вообще существует. Поэтому в
выходе стоит и сам домен, и из какого поля он взят, а не голая строка.

Запуск на сервере: пишет `C:\sender\_ops\3s_p25_sayty.csv` и печатает счёт.
"""
import collections
import csv
import json
import re
import sqlite3

BAZA = 'file:C:/seostat/data/p25.db?mode=ro'
VYHOD = r'C:\sender\_ops\3s_p25_sayty.csv'

# Домен принадлежит почтовику, а не предприятию.
POCHTOVIKI = {
    'mail.ru', 'yandex.ru', 'ya.ru', 'gmail.com', 'bk.ru', 'inbox.ru', 'list.ru',
    'rambler.ru', 'internet.ru', 'narod.ru', 'googlemail.com', 'outlook.com',
    'hotmail.com', 'icloud.com', 'yahoo.com', 'mail.com', 'bk.ru', 'yandex.com',
    'sberbank.ru', 'rt.ru', 'vk.com', 'mvd.ru',
}
ADRES = re.compile(r'[\w.+-]+@([\w-]+(?:\.[\w-]+)+)')


def main():
    b = sqlite3.connect(BAZA, uri=True)
    sch = collections.Counter()
    ryady = []
    for inn, predpr, pochta, pochty_ch, sayt in b.execute(
            'select inn, coalesce(predpriyatie,""), coalesce(pochta,""), '
            'coalesce(pochty_checko,""), coalesce(sayt,"") from company'):
        sch['предприятий'] += 1
        if sayt.strip():
            sch['sayt уже заполнен'] += 1
        naydeno = []
        for pole, ist in ((pochta, 'pochta'), (pochty_ch, 'pochty_checko')):
            for m in ADRES.finditer(pole):
                d = m.group(1).lower()
                d = d[4:] if d.startswith('www.') else d
                if d in POCHTOVIKI:
                    sch['адрес на публичном почтовике — домен не берём'] += 1
                    continue
                if (d, ist) not in naydeno:
                    naydeno.append((d, ist))
        if not naydeno:
            sch['корпоративной почты нет — домена не добыть'] += 1
            continue
        # Домен, встретившийся у предприятия чаще, надёжнее случайного одиночного.
        chastota = collections.Counter(d for d, _ in naydeno)
        d, _ = naydeno[0]
        d = chastota.most_common(1)[0][0]
        ist = ', '.join(sorted({i for dd, i in naydeno if dd == d}))
        sch['ДОМЕН ДОБЫТ'] += 1
        if len(chastota) > 1:
            sch['доменов у предприятия несколько — взят частый'] += 1
        ryady.append({'inn': inn, 'predpriyatie': predpr, 'sayt': d,
                      'otkuda': 'домен корпоративной почты (' + ist + ')',
                      'vseh_domenov': len(chastota),
                      'vse_domeny': ' | '.join(sorted(chastota))})

    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, delimiter=';', fieldnames=[
            'inn', 'predpriyatie', 'sayt', 'otkuda', 'vseh_domenov', 'vse_domeny'])
        w.writeheader()
        w.writerows(ryady)
    for z in ryady[:8]:
        print('REC ' + json.dumps(z, ensure_ascii=False))
    print('ИТОГ ' + json.dumps({'файл': VYHOD, 'строк': len(ryady),
                                'счёт': dict(sch.most_common())}, ensure_ascii=False))


if __name__ == '__main__':
    main()
