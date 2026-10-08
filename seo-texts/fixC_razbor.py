# -*- coding: utf-8 -*-
"""fixC: разбор страниц-источников номеров (подписи людей, должности, добавочные, мусор).

Только детерминированные правила, без модели. Используется из fixC_podpisi.py (локально,
по скачанным страницам) — в каталог сам не пишет.

  * html_v_tekst(html)  -> (текст со строками и метками ⟦tel:…⟧, текст из <!-- комментариев -->)
  * nomera_v_tekste(t)  -> вхождения номеров: позиция, 10 цифр, добавочный, из ссылки tel: или видимый
  * podpis(t, vh, k)    -> текст подписи перед k-м номером (подпись соседа не берётся)
  * fio_i_dolzhnost(s)  -> (ФИО, должность) из подписи; неоднозначное -> пусто
"""
import html as _html
import re
from html.parser import HTMLParser

BLOK = {'p', 'div', 'li', 'ul', 'ol', 'tr', 'table', 'tbody', 'thead', 'h1', 'h2', 'h3', 'h4', 'h5',
        'h6', 'section', 'article', 'header', 'footer', 'nav', 'aside', 'main', 'form', 'address',
        'dl', 'dt', 'dd', 'blockquote', 'pre', 'figure', 'figcaption', 'br', 'hr', 'option', 'label',
        'center', 'caption'}
YACH = {'td', 'th'}
PROPUSK = {'script', 'style', 'noscript', 'svg', 'template', 'head', 'iframe', 'select'}


class _Tekst(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.komm = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in PROPUSK:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in BLOK:
            self.out.append('\n')
        elif tag in YACH:
            self.out.append(' | ')
        if tag == 'a':
            href = dict(attrs).get('href') or ''
            if href.lower().replace(' ', '').startswith(('tel:', 'callto:')):
                self.out.append(' ⟦tel:%s⟧ ' % _html.unescape(href.split(':', 1)[1]).strip())

    def handle_startendtag(self, tag, attrs):
        if tag in ('br', 'hr') and not self.skip:
            self.out.append('\n')
        elif tag == 'a':
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in PROPUSK:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in BLOK:
            self.out.append('\n')
        elif tag in YACH:
            self.out.append(' | ')

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)

    def handle_comment(self, data):
        self.komm.append(data)


def dekodirovat(b, ct=''):
    m = re.search(r'charset=([\w-]+)', ct or '', re.I)
    kandidaty = []
    if m:
        kandidaty.append(m.group(1))
    m2 = re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', b[:5000], re.I)
    if m2:
        kandidaty.append(m2.group(1).decode('ascii', 'ignore'))
    kandidaty += ['utf-8', 'cp1251']
    for k in kandidaty:
        try:
            return b.decode(k)
        except (LookupError, UnicodeDecodeError):
            continue
    return b.decode('utf-8', 'replace')


def html_v_tekst(h):
    p = _Tekst()
    try:
        p.feed(h)
        p.close()
    except Exception:  # noqa: BLE001
        pass
    t = ''.join(p.out).replace('\xa0', ' ').replace('\u200b', '')
    t = re.sub('[\u2010\u2011\u2012\u2013\u2212]', '-', t)       # «00‒00‒00»: тире-цифры как дефис
    stroki = []
    for s in t.split('\n'):
        s = re.sub(r'[ \t\r\f\v]+', ' ', s).strip()
        s = re.sub(r'^(?:\|\s*)+|(?:\s*\|)+$', '', s).strip()
        s = re.sub(r'(?:\s*\|\s*){2,}', ' | ', s)
        if s:
            stroki.append(s)
    komm = '\n'.join(p.komm)
    return '\n'.join(stroki), komm


# ------------------------------------------------------------------ номера в тексте
# Видимый номер: 10–11 цифр с разделителями (пробел, дефис, точка, скобки), в т. ч. код
# города с дефисом «(341-41)» — его прежний разбор не понимал (ГКЗ, kombi-korm.ru).
_NOMER = re.compile(r'(?<![\d\w])(?:\+\s?\d{1,3}|8)?[\s\-.]*\(?\s*\d{2,5}(?:[\s\-]\d{1,3})?\s*\)?[\s\-.]*\d{1,4}(?:[\s\-.]*\d{1,4}){1,4}(?![\d])')
_DOB = re.compile(r'^[\s,;:]*[(\[]?\s*(?:доб(?:авочн\w*)?|доп|вн(?:утр\w*)?|ext)\.?\s*:?\s*[(\[]?\s*(\d{2,5})(?:\s*[,/и]\s*\d{2,5})*\s*[)\]]?', re.I)
_TEL = re.compile(r'⟦tel:([^⟧]*)⟧')


def cifry(s):
    return re.sub(r'\D', '', s or '')


def klyuch10(d):
    """10 цифр российского номера из строки цифр (11 с 7/8 или 10); иначе ''."""
    if len(d) == 11 and d[0] in '78':
        return d[1:]
    if len(d) == 10:
        return d
    return ''


def nomera_v_tekste(t):
    """Все вхождения номеров: dict(nach, kon, k10, cifry, dob, tel, syroy, stroka)."""
    vh = []
    zanyato = []
    for m in _TEL.finditer(t):
        d = cifry(m.group(1))
        vh.append({'nach': m.start(), 'kon': m.end(), 'cifry': d, 'k10': klyuch10(d), 'dob': '',
                   'tel': True, 'syroy': m.group(1)})
        zanyato.append((m.start(), m.end()))
    for m in _NOMER.finditer(t):
        if any(a <= m.start() < b for a, b in zanyato):
            continue
        s = m.group(0)
        d = cifry(s)
        if len(d) < 10 or len(d) > 12:
            continue
        if re.search(r'\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4}', s):     # дата, не номер
            continue
        if re.search(r'(?i)(?:инн|огрн\w*|кпп|окпо|окато|октмо|бик|р/с|к/с|сч[её]т|mcode|артикул|арт\.)[\s:№#-]{0,4}$',
                     t[max(0, m.start() - 14):m.start()]):
            continue                                  # реквизит или артикул, не телефон
        dob = ''
        md = _DOB.match(t[m.end():m.end() + 30])
        kon = m.end()
        if md:
            dob = md.group(1)
            kon = m.end() + md.end()
        vh.append({'nach': m.start(), 'kon': kon, 'cifry': d, 'k10': klyuch10(d), 'dob': dob,
                   'tel': False, 'syroy': s.strip()})
    vh.sort(key=lambda x: x['nach'])
    return vh


# ------------------------------------------------------------------ подпись перед номером
_EMAIL = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
_SHUM = re.compile(r'(?i)\b(?:тел(?:ефон)?(?:ы)?|т|моб(?:ильный)?|сот(?:овый)?|раб(?:очий)?|tel|phone|e-?mail|'
                   r'почта|эл\.? ?почта|контакт\w*|звонит\w*|позвонить|связ\w*|номер|для связи|многоканальный|'
                   r'whatsapp|viber|telegram|ватсап|вайбер)\b\.?')


def _chistyy(s):
    s = _TEL.sub(' ', s)
    s = _EMAIL.sub(' ', s)
    s = re.sub(r'(?i)(?:доб|доп)\.?\s*\(?\d{2,5}\)?', ' ', s)
    return s


def _soderzhatelnyy(s):
    """Есть ли в куске слова кроме шума (тел., моб., e-mail, двоеточия)."""
    s = _SHUM.sub(' ', _chistyy(s))
    return bool(re.search(r'[А-Яа-яЁёA-Za-z]{3,}', s))


def _posle_tire(s):
    """Подпись ПОСЛЕ номера в виде «… – приёмная» / «… (бухгалтерия)»."""
    m = re.match(r'^\s*(?:[-–—]\s*|\(\s*)([А-Яа-яЁё][^()\n|\d⟦]{2,60})', s)
    if m and not re.match(r'(?i)\s*(?:доб|доп|вн)', m.group(1)):
        return m.group(1).strip(' ,;.)')
    return ''


_ADRES = re.compile(r'(?i)(?:\b(?:обл|область|край|район|р-н|р-он|ул|улица|пр-т|проспект|шоссе|пер|переулок|'
                    r'д|дер|пос|п|с|г|мкр|стр|корп|оф|пом|зд|литер\w*)\.?\s|\b\d{6}\b|https?://|www\.|сайт\b|'
                    r'(?:пн|вт|ср|чт|пт|сб|вс)\b.*\d{1,2}[:.]\d{2}|\d{1,2}[:.]\d{2}\s*[-–—]\s*\d{1,2}[:.]\d{2})')


def _adres_li(s):
    """Строка адреса, часов работы или ссылки на сайт – не подпись: её пропускаем."""
    return bool(_ADRES.search(s)) and not _DOLZH_NACH.search(re.sub(_ADRES, ' ', s) if False else s[:25])


def _stroki_podpisi(mezhdu):
    """Строки между двумя номерами без ссылок, почты, добавочных и строк-шума («Телефон:»)."""
    t = _TEL.sub('\n', mezhdu)
    t = _EMAIL.sub('\n', t)
    t = re.sub(r'(?i)[(\[]?\s*(?:доб|доп)\.?\s*:?\s*\(?\d{2,5}\)?(?:\s*[,/и]\s*\d{2,5})*\s*[)\]]?', '\n', t)
    out = []
    for s in t.split('\n'):
        s = s.strip(' |,;')
        if s and _soderzhatelnyy(s):
            out.append(s)
    return out


def podpis(t, vh, k, glubina=3):
    """Подпись k-го вхождения: последние 3 содержательные строки между предыдущим номером
    и этим (не длиннее 200 знаков). Подпись соседа не берётся: граница – предыдущий номер
    или почта. Если между номерами только «тел.», добавочный или ссылка – это второй номер
    того же человека, подпись общая с предыдущим. Подпись ПОСЛЕ предыдущего номера через
    тире («… – приёмная») принадлежит ему, а не нам."""
    x = vh[k]
    # одна и та же цифра дважды (ссылка tel: и видимый текст) – это одно вхождение
    j = k - 1
    while j >= 0 and vh[j]['kon'] > x['nach'] - 3 and vh[j]['k10'] == x['k10']:
        j -= 1
    nach = vh[j]['kon'] if j >= 0 else max(0, x['nach'] - 400)
    mezhdu = t[nach:x['nach']]
    if j >= 0:
        pt = _posle_tire(mezhdu)
        if pt:
            mezhdu = mezhdu.split(pt, 1)[1] if pt in mezhdu else ''
    stroki = [x[-150:] for x in _stroki_podpisi(mezhdu) if not _adres_li(x)]
    if stroki:
        return '\n'.join(stroki[-3:]), 'pered'
    # своя подпись после номера через тире
    pt = _posle_tire(t[x['kon']:x['kon'] + 80])
    if pt:
        return pt, 'posle'
    if j >= 0 and glubina > 0 and len(mezhdu) < 80:
        # два номера одного человека подряд: подпись предыдущего, если он не подписан
        # «после» (тогда страница подписывает номера справа)
        if not _posle_tire(t[vh[j]['kon']:vh[j]['kon'] + 80]):
            p, kak = podpis(t, vh, j, glubina - 1)
            return p, (kak + '+sosed_nomer') if p else ''
    return '', ''


def _metka_li(stroka):
    """Похожа ли строка на подпись (должность/отдел или ФИО)."""
    return bool(stroka) and (bool(dolzhnost_iz(stroka)) or bool(najti_fio(stroka)[0]))


def razmetka(t, vh):
    """Подписи всех номеров страницы с учётом раскладки списка. -> {индекс vh: (подпись, как)}.

    Списки бывают двух видов: «Отдел кадров / номер / Отдел снабжения / номер» (подпись
    ПЕРЕД номером) и «номер / Отдел кадров / номер / Отдел снабжения» (подпись ПОСЛЕ).
    По одному номеру их не различить, по списку целиком – можно: если перед первым номером
    подписи нет (заголовок «Телефоны:»), а после последнего она есть, – подпись после.
    Прежний разбор знал только «перед» и в списках второго вида отдавал номеру подпись
    соседа сверху. Подпись в той же строке сразу за номером («36-4-99 факс») – своя у номера."""
    ed = []
    for i, x in enumerate(vh):
        if ed and x['k10'] == vh[ed[-1][-1]]['k10'] and x['nach'] - vh[ed[-1][-1]]['kon'] <= 3:
            ed[-1].append(i)
        else:
            ed.append([i])
    nach = [vh[e[0]]['nach'] for e in ed]
    kon = [max(vh[i]['kon'] for i in e) for e in ed]

    def mezhdu(a, b):
        return [x for x in _stroki_podpisi(t[a:b]) if not _adres_li(x)]

    def konec_stroki(j):
        k = t.find('\n', kon[j])
        return len(t) if k < 0 else k

    def v_stroke(j):
        """Своя подпись в той же строке после номера (не «Бухгалтерия:» – та для следующего)."""
        if j + 1 < len(ed) and nach[j + 1] < konec_stroki(j):
            return ''              # в строке дальше другой номер: хвост скорее его подпись
        hvost = _chistyy(t[kon[j]:konec_stroki(j)]).strip(' ,;|–—-()')
        if not hvost or hvost.endswith(':') or len(hvost.split()) > 4 or najti_fio(hvost)[0]:
            return ''
        return hvost if _metka_li(hvost) else ''

    progony, tek = [], [0] if ed else []
    for j in range(1, len(ed)):
        m = t[kon[j - 1]:nach[j]]
        stroki = [x for x in m.split('\n') if x.strip()]
        if len(stroki) <= 3 and all(len(x) <= 80 for x in stroki) and len(m) < 240:
            tek.append(j)
        else:
            progony.append(tek)
            tek = [j]
    if tek:
        progony.append(tek)
    out = {}
    for pr in progony:
        rezhim = 'pered'
        if len(pr) >= 2:
            pered1 = mezhdu(kon[pr[0] - 1] if pr[0] > 0 else max(0, nach[pr[0]] - 300), nach[pr[0]])
            posle_n = mezhdu(konec_stroki(pr[-1]), min(len(t), konec_stroki(pr[-1]) + 160))[:2]
            lb = _metka_li(pered1[-1]) if pered1 else False
            la = _metka_li(posle_n[0]) if posle_n else False
            # «подпись после» – только у простого списка: между номерами не больше одной
            # строки, и подпись за последним номером не стоит прямо перед следующим номером
            vnutr = [len(mezhdu(kon[pr[n]], nach[pr[n + 1]])) for n in range(len(pr) - 1)]
            sled_blizko = (pr[-1] + 1 < len(ed)) and len(
                [x for x in t[kon[pr[-1]]:nach[pr[-1] + 1]].split('\n') if x.strip()]) <= 2
            if la and not lb and max(vnutr or [0]) <= 1 and not sled_blizko:
                rezhim = 'posle'
        for n, j in enumerate(pr):
            svoya = v_stroke(j)
            for i in ed[j]:
                if svoya:
                    out[i] = (svoya, 'v_stroke_posle')
                elif rezhim == 'posle':
                    sled = nach[pr[n + 1]] if n + 1 < len(pr) else min(len(t), kon[j] + 160)
                    st = mezhdu(konec_stroki(j), max(sled, konec_stroki(j)))[:2]
                    out[i] = ('\n'.join(reversed(st)), 'posle_spisok') if st else ('', '')
                else:
                    p_, kak = podpis(t, vh, i)
                    # подпись «перед» не должна быть чужой подписью «в строке» предыдущего номера
                    if p_ and j > 0 and v_stroke(j - 1) and p_.strip() == v_stroke(j - 1).strip():
                        p_, kak = '', ''
                    out[i] = (p_, kak)
    return out


# ------------------------------------------------------------------ ФИО и должность
IMENA = set('''александр алексей анатолий андрей антон аркадий арсений артем артём артур борис вадим валентин
валерий василий виктор виталий владимир владислав вячеслав геннадий георгий герман глеб григорий даниил
данил денис дмитрий евгений егор иван игорь илья иосиф кирилл константин лев леонид максим марат матвей
михаил назар никита николай олег павел петр пётр роберт родион роман руслан рустам семен семён сергей
станислав степан тимофей тимур федор фёдор филипп эдуард юрий яков ярослав ильдар ильгам ильдус айдар
азат ринат рафаэль рамиль равиль радик раис ильнур булат фарид шамиль камиль марсель альберт эльдар
расул магомед ахмед мурат хасан ислам аслан заур тагир салават фаниль нурлан ерлан акиф
александра алена алёна алина алла анастасия ангелина анна антонина валентина валерия вера вероника
виктория галина дарья диана ева евгения екатерина елена елизавета жанна зинаида зоя инна ирина карина
кира клавдия кристина ксения лариса лидия любовь людмила маргарита марина мария надежда наталья наталия
нина оксана ольга полина раиса регина светлана снежана софия софья таисия тамара татьяна ульяна эльвира
юлия яна гульшат гульнара гузель альбина лилия ляйсан алсу флюра венера резеда айгуль динара фарида
ильмира розалия эльмира асия зульфия наиля рузиля лейла мадина'''.split())
_OTCH = re.compile(r'^[А-ЯЁ][а-яё]+(?:ович|евич|ич|овна|евна|ична|инична)$|^(?:оглы|кызы|Оглы|Кызы)$')
_SLOVO = r'[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?'
_INIC = r'[А-ЯЁ]\.\s?[А-ЯЁ]\.?'
FIO_RE = [
    # перекрывающийся поиск (?=…): «Директор Александр Сурков» – пара «Александр Сурков»
    # иначе не проверялась бы, её съедала неудачная пара «Директор Александр»
    re.compile(r'(?<![А-Яа-яЁё])(?=(%s)\s+(%s)\s+(%s)(?:\s+(?:оглы|кызы|Оглы|Кызы))?)' % (_SLOVO, _SLOVO, _SLOVO)),
    re.compile(r'(?<![А-Яа-яЁё])(?=(%s)\s+(%s))' % (_SLOVO, _INIC)),            # Фамилия И.О.
    re.compile(r'(?<![А-Яа-яЁё.])(?=(%s)\s*(%s))' % (_INIC, _SLOVO)),          # И.О. Фамилия
    re.compile(r'(?<![А-Яа-яЁё])(?=(%s)\s+(%s))' % (_SLOVO, _SLOVO)),           # Имя Фамилия / Фамилия Имя
]

# Начала должностей и подразделений: от первого такого слова и до ФИО/конца — должность.
_DOLZH_NACH = re.compile(
    r'(?i)(?<![А-Яа-яЁё])(?:генеральн|гендиректор|исполнительн|коммерческ|техническ|финансов|'
    r'главн\w*\s+(?:инженер|механик|энергетик|технолог|бухгалтер|специалист|экономист|агроном|зоотехник|'
    r'юрист|юрисконсульт|ветврач|врач|конструктор|офис|менеджер|приемн|приёмн|управлен|диспетчер|метролог|'
    r'архитектор|аналитик|эксперт|ревизор|кассир)|гл\.|'
    r'заместител|зам\.|первый зам|начальник|нач\.|руководител|рук\.|директор|управляющ|председател|'
    r'президент|заведующ|зав\.|менеджер|специалист|инженер|механик|энергетик|технолог|бухгалтер|'
    r'экономист|юрист|юрисконсульт|секретар|приемн|приёмн|отдел|служб|департамент|управлени|дирекци|'
    r'лаборатор|склад|канцеляр|офис|диспетчер|оператор|кадр|снабжен|закуп|продаж|сбыт|маркет|реклам|'
    r'логист|транспорт|охран|факс|горяч|справочн|бригадир|мастер|контролер|контролёр|агроном|зоотехник|'
    r'ветеринар|кладовщик|кассир|администратор|помощник|ассистент|аналитик|координатор|эколог|'
    r'энергослужб|ремонт|сервис|производств|цех|омтс|мтс|мто|огм|огэ|хозяйств|снабжени|заготов|'
    r'приемк|приёмк|поставщик|экскурс|магазин|опт|розниц|бухгалтери|по вопросам|собственник|владел|'
    r'учредител|основател|секретариат|ведущ|старш|маркетолог|логист|технолог|юрисконсульт|инспектор|'
    r'эксперт|общий|единый|справочн|горяч|для |сотрудник|представител|телефакс)')


def _imya_li(w):
    return w.lower().replace('ё', 'е') in {i.replace('ё', 'е') for i in IMENA}


def najti_fio(s):
    """ФИО в строке подписи: (ФИО, начало, конец) или ('', -1, -1). Двухсловная пара берётся
    только со словарным именем (иначе «Отдел Продаж» стал бы человеком). Из нескольких – самое
    правое (ближе к номеру)."""
    for n, rx in enumerate(FIO_RE):
        luchshee = None
        for m in rx.finditer(s):
            g = [x for x in m.groups() if x]
            if n == 0:
                ogly = bool(re.match(r'\s+(?:оглы|кызы|Оглы|Кызы)\b', s[m.start() + len(' '.join(g)):]))
                ok = (((_OTCH.match(g[2]) or ogly) and not _DOLZH_NACH.match(g[0]) and not _DOLZH_NACH.match(g[1]))
                      or (_OTCH.match(g[1]) and _imya_li(g[0]) and not _DOLZH_NACH.match(g[2])))
            elif n in (1, 2):
                fam = g[0] if n == 1 else g[1]
                ok = not _DOLZH_NACH.match(fam) and len(fam) >= 3
            else:
                ok = ((_imya_li(g[0]) or _imya_li(g[1])) and not (_imya_li(g[0]) and _imya_li(g[1]))
                      and not _DOLZH_NACH.match(g[0]) and not _DOLZH_NACH.match(g[1]))
            if ok:
                tekst = ' '.join(g) if n != 2 else (g[0] + ' ' + g[1])
                if n == 0 and re.match(r'\s+(?:оглы|кызы|Оглы|Кызы)', s[m.start() + len(' '.join(g)):]):
                    tekst += s[m.start() + len(' '.join(g)):].split()[0].join([' ', ''])
                kon = m.start() + len(tekst)
                luchshee = (tekst.strip(), m.start(), kon)
        if luchshee:
            return luchshee
    return '', -1, -1


def dolzhnost_iz(s):
    """Должность/подразделение в одной строке: от первого слова-должности до конца.
    Длинная строка (проза, меню) – не подпись: должность не берётся."""
    s = re.sub(r'\s+', ' ', _SHUM.sub(' ', s or '')).strip(' :|,;.-–—')
    if not s or len(s) > 110:
        return ''
    m = _DOLZH_NACH.search(s)
    if not m:
        return ''
    # перед должностью – не больше двух слов («Ведущий», «Наш», «КОНТАКТЫ»)
    if len(s[:m.start()].split()) > 2:
        return ''
    nach = m.start()
    pm = re.search(r'(?i)(?:ведущ\w*|старш\w*|младш\w*|и\.?\s?о\.?|врио)\s+$', s[:nach])
    if pm:
        nach = pm.start()
    # «Экспортный отдел», «Коммерческая служба»: прилагательное перед словом-должностью – её часть
    pm = re.search(r'(?i)(?:[а-яё-]+(?:ый|ий|ой|ая|яя|ое|ее|ые|ие)\s+){1,2}$', s[:nach])
    if pm:
        nach = pm.start()
    d = s[nach:].strip(' :|,;.-–—')[:120]
    # «Адрес производства», «Сеть магазинов» – не должность: одно слово в родительном падеже
    # после другого слова
    if re.fullmatch(r'[а-яё]+(?:а|ов|ей|ии|ых|ия)', d):
        return ''
    d = re.sub(r'[\s:,;(]*\+?\d[\d\s()+-]*$|[\s:,;]*\($', '', d).strip(' :|,;.-–—')   # «Отдел кадров: 7(»
    return d


def fio_i_dolzhnost(podp):
    """(ФИО, должность) из подписи (строки, ближняя к номеру – последняя). Должность и ФИО
    ищутся в ближней строке и в соседней с ФИО; дальше не идём (там меню и заголовки)."""
    L = []
    for x in (podp or '').split('\n'):
        x = re.sub(r'(?i)(тел\w*\.?|телефон)\s*/\s*факс', 'телефакс', x)
        # сильные разделители внутри строки: «Instagram --> Директор …», «… | Главный инженер»
        kuski = [k.strip() for k in re.split(r'-->|\s\|\s|•|·|»\s|\s{3,}', x) if k.strip()]
        if kuski:
            L.append(kuski[-1] if len(kuski[-1]) > 2 else x.strip())
    if not L:
        return '', ''
    # «Тел./факс:» прямо над номером – не подпись, если выше есть настоящая
    if len(L) >= 2 and re.fullmatch(r'(?i)\W*телефакс\W*', L[-1]):
        f2, d2 = fio_i_dolzhnost('\n'.join(L[:-1]))
        if f2 or d2:
            return f2, d2
    fio, a, b = najti_fio(L[-1])
    if not fio and re.fullmatch(r'[А-ЯЁ][а-яё]+', L[-1].strip(' :,')) and _imya_li(L[-1].strip(' :,')):
        fio, a, b = L[-1].strip(' :,'), 0, len(L[-1])          # только имя: «Юлия»
    if fio:
        ost = (L[-1][:a] + ' ' + L[-1][b:]).strip()
        d = dolzhnost_iz(ost)
        if (not d or re.fullmatch(r'(?i)\W*телефакс\W*', d)) and len(L) >= 2:
            d = dolzhnost_iz(L[-2]) or d
        return fio, d
    d = dolzhnost_iz(L[-1])
    if len(L) >= 2:
        f2, a2, b2 = najti_fio(L[-2])
        # строка выше – одно ФИО (без лишнего текста): «Иванов И. И. / Главный инженер / номер»
        if f2 and len((L[-2][:a2] + L[-2][b2:]).strip(' :,-–—')) <= 3:
            if d:
                return f2, d
            # «Сибикеев Константин / Специи, оболочки, дезинфицирующие средства / номер» –
            # участок работы вместо должности: берём его как есть (роль решит классификатор)
            kus = L[-1].strip(' :,-–—')
            if 3 <= len(kus) <= 70 and not re.search(r'\d', kus) and not _adres_li(kus):
                return f2, kus
    return '', d


# ------------------------------------------------------------------ люди страницы (запись «должность – ФИО – контакты»)
_KOROTKIY = re.compile(r'(?<![\d\w])\d{1,3}-\d{2}-\d{2}(?![\d])')
_OTZYV = re.compile(r'(?i)благодар|отзыв|рекоменд|выражает|сотрудничаем с|работаем с|клиент[ыа]?\b|партн[её]р[ыа]?\b')


def _tip_stroki(s):
    """F – одно ФИО, D – одна должность, FD – обе в строке, N – полный номер, n – местный номер."""
    s0 = re.sub(r'(?i)^\s*(?:ФИО|ф\.и\.о\.)\s*:\s*', '', s).strip(' /')
    if nomera_v_tekste(s0) and any(x['k10'] for x in nomera_v_tekste(s0)):
        return 'N'
    if len(s0) > 100:
        return ''
    fio, a, b = najti_fio(s0)
    d = dolzhnost_iz((s0[:a] + ' ' + s0[b:]) if fio else s0)
    if fio and d:
        return 'FD'
    if fio and len((s0[:a] + s0[b:]).strip(' :,;-–—/')) <= 3:
        return 'F'
    if d and not fio:
        return 'D'
    if _KOROTKIY.search(s0):
        return 'n'
    return ''


def lyudi_stranicy(t):
    """Записи «должность + ФИО» страницы и что за ними до следующей записи: полные номера
    (10 цифр), местные номера без кода («2-49-35»), почта. Раскладка «ФИО над должностью» или
    «должность над ФИО» определяется по странице целиком (по однозначным парам)."""
    L = [x.strip() for x in t.split('\n')]
    L = [x for x in L if x]
    tip = [_tip_stroki(x) for x in L]
    fd = dp = 0
    for i in range(len(L)):
        if tip[i] == 'D':
            pr = tip[i - 1] if i > 0 else ''
            sl = tip[i + 1] if i + 1 < len(L) else ''
            if pr == 'F' and sl != 'F':
                fd += 1
            elif sl == 'F' and pr != 'F':
                dp += 1
    fio_pervym = fd > dp
    zapisi = []
    zanyat = set()
    for i in range(len(L)):
        if tip[i] == 'FD':
            fio, a, b = najti_fio(re.sub(r'(?i)^\s*ФИО\s*:\s*', '', L[i]))
            s0 = re.sub(r'(?i)^\s*ФИО\s*:\s*', '', L[i])
            zapisi.append((i, i, fio, dolzhnost_iz(s0[:a] + ' ' + s0[b:])))
        elif tip[i] == 'D':
            kand = [i - 1, i + 1] if fio_pervym else [i + 1, i - 1]
            for j in kand:
                if 0 <= j < len(L) and tip[j] == 'F' and j not in zanyat:
                    # «Должность / Должность / ФИО / ФИО» – пара неоднозначна, пропускаем
                    if (j == i + 1 and i > 0 and tip[i - 1] == 'D') or (j == i - 1 and i + 1 < len(L) and tip[i + 1] == 'D'):
                        break
                    fio = najti_fio(re.sub(r'(?i)^\s*ФИО\s*:\s*', '', L[j]))[0]
                    zanyat.add(j)
                    zapisi.append((min(i, j), max(i, j), fio, dolzhnost_iz(L[i])))
                    break
    zapisi.sort()
    out = []
    for n, (a, b, fio, dolzh) in enumerate(zapisi):
        konec = zapisi[n + 1][0] if n + 1 < len(zapisi) else min(len(L), b + 6)
        konec = min(konec, b + 6)
        # хвост записи – только строки «номер/почта» без своей подписи; строка «Приёмная – номер»
        # или новая должность – уже другая запись
        for j in range(b + 1, konec):
            if tip[j] in ('D', 'F', 'FD'):
                konec = j
                break
            ostatok = re.sub(r'(?i)факс|fax', ' ', re.sub(r'[\d()+\-.,;:/ ]+', ' ', _chistyy(L[j])))
            if tip[j] == 'N' and _soderzhatelnyy(ostatok):
                konec = j
                break
        nomera, korotkie = [], []
        for j in range(b + 1, konec):
            vh_ = nomera_v_tekste(L[j])
            for x in vh_:
                if x['k10'] and not x['tel'] and not re.search(r'(?i)факс|fax', L[j][max(0, x['nach'] - 12):x['nach']]):
                    nomera.append((x['k10'], x['dob']))
            if not [x for x in vh_ if x['k10']]:
                korotkie += _KOROTKIY.findall(L[j])
        okolo = '\n'.join(L[max(0, a - 3):konec])
        stroka = L[a] + ' ' + L[b]
        out.append({'fio': fio, 'dolzh': dolzh, 'nomera': nomera, 'korotkie': korotkie,
                    'pochta': _EMAIL.findall('\n'.join(L[b + 1:konec])),
                    'otzyv': bool(_OTZYV.search(okolo)) or bool(re.search(r'(?i)блог|новост|стать', stroka)),
                    'tekst': '\n'.join(L[max(0, a - 1):konec])[:400]})
    return out
