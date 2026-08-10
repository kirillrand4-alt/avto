# -*- coding: utf-8 -*-
"""574 факта держатся на ПЕРЕЧНЕ заключений предприятия, а не на конкретном заключении.
Вторая версия — после того, как первая уткнулась и обе догадки оказались неверны.

Что выяснено пробами, а не предположено:
  * ссылок вида /conclusion/<id> в разметке перечня НЕТ (строки раскрываются кнопкой),
    но сами адреса ЖИВЫ: /conclusion/25-ТУ-03953-2018 отдаёт 200, номер и эксплуатант
    на странице. Значит адрес надо СОБРАТЬ из номера заключения, а не искать в href;
  * номер заключения виден прямо в строке перечня («2-ТУ-899208-2026»);
  * перечень листается через &page=N по 25 строк, но у крупного завода их 10 644 —
    листать нельзя;
  * у перечня ЕСТЬ поиск, имя параметра `q` (взято из поля ввода на странице,
    не угадано): `?exploiter=ИНН&q=компрессор` сузило 10 644 -> 149.

Отсюда способ: ищем по ЗАВОДСКОМУ НОМЕРУ факта — он в перечне печатается в описании
объекта. Если заводского номера нет, ищем по типу машины и сверяем описание.

Пишем в C:\\sender\\park_perechen2.jsonl с fsync, резюм по id факта.
Запуск: panel_py, argv = [<сколько фактов за вызов>]
"""
import json, os, re, sys, time
from urllib.parse import quote

BAZA = r'C:\sender'
ZAD = r'C:\seostat\drop\drop-storage\park_perechen_zadanie.json'
OUT = os.path.join(BAZA, 'park_perechen2.jsonl')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
_NOM = re.compile(r'\b\d{1,3}-[А-ЯЁ]{2}-\d{3,7}-\d{4}\b')
# описание объекта = строка без номера заключения, даты и названия эксплуатанта:
# именно в нём стоит «зав. № …», и именно его нельзя путать с номером заключения
NASHE = re.compile(
    r'компрессор|воздуходувк|газодувк|турбокомпрессор|нагнетател|воздухораздел|'
    r'ресивер|осушител|воздухосборник|(генератор\w{0,4}\s*(азота|кислорода))|'
    r'(сжат\w{0,4}\s*воздух)|компрессорн|влагоотделител|маслоотделител')
_ZAVNOM = re.compile(r'зав\w*\.?\s*(?:№|N|номер)\s*([A-Za-zА-Яа-я0-9\-/]{1,20})', re.I)


def _OPISANIE(t):
    """убираем начало строки: номер заключения, дату и кавычки с именем организации"""
    t = _NOM.sub(' ', t or '')
    t = re.sub(r'\b\d{2}\.\d{2}\.\d{4}\b', ' ', t)
    t = re.sub(r'(ООО|АО|ПАО|ЗАО|ОАО|АК|НАО)\s*«[^»]{0,80}»|'
               r'(ООО|АО|ПАО|ЗАО|ОАО|АК|НАО)\s*"[^"]{0,80}"', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


def _ZAV_SPISOK(opisanie):
    """заводские номера ИЗ «зав. № X», нормализованные. Сравнивать надо ЦЕЛИКОМ:
    подстрока «407» находится в номере заключения 614407 и даёт чужой документ."""
    return {_norm_zav(m) for m in _ZAVNOM.findall(opisanie or '') if _norm_zav(m)}


def _norm_zav(s):
    return re.sub(r'[^A-Za-zА-Яа-я0-9]', '', (s or '')).upper()
_TEG = re.compile(r'<[^>]+>')


def _hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e
    return None


def _sdelano():
    v = set()
    if os.path.exists(OUT):
        with open(OUT, encoding='utf-8', errors='replace') as f:
            for ln in f:
                try:
                    v.add(json.loads(ln)['fakt_id'])
                except Exception:
                    pass
    return v


def _zapisat(s):
    with open(OUT, 'a', encoding='utf-8') as f:
        f.write(json.dumps(s, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


def _cifry(s):
    return re.sub(r'\D', '', s or '')


def main():
    skolko = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    zad = json.load(open(ZAD, encoding='utf-8'))
    # задание: {инн: [{fakt_id, zav, tekst}, ...]}
    plosk = []
    for inn, spisok in zad.items():
        for f in spisok:
            plosk.append({'inn': inn, **f})
    gotovo = _sdelano()
    # сначала те, у кого есть заводской номер: по нему поиск точный
    plosk.sort(key=lambda x: (0 if (x.get('zav') or '').strip() else 1, x['fakt_id']))
    ochered = [x for x in plosk if x['fakt_id'] not in gotovo][:skolko]
    itog = {'faktov_v_zadanii': len(plosk), 'sdelano_ranee': len(gotovo),
            'v_etom_vyzove': len(ochered), 'nashli_zaklyuchenie': 0,
            'ne_nashli': 0, 'oshibki': []}
    if not ochered:
        print(json.dumps(itog, ensure_ascii=False))
        return
    from playwright.sync_api import sync_playwright
    exe = _hrom()
    with sync_playwright() as p:
        kw = {'headless': True, 'args': ['--no-sandbox']}
        if exe:
            kw['executable_path'] = exe
        br = p.chromium.launch(**kw)
        pg = br.new_context(user_agent=UA, locale='ru-RU',
                            ignore_https_errors=True).new_page()
        for f in ochered:
            zav = (f.get('zav') or '').strip()
            # короткий заводской номер («407», «350») как поисковое слово бесполезен:
            # он встречается внутри номеров заключений. Тогда ищем по типу машины,
            # а заводской номер сверяем уже в описании найденных строк.
            slovo = zav if len(re.sub(r'[^A-Za-z0-9А-Яа-я]', '', zav)) >= 4 else 'компрессор'
            u = ('https://monitor-pb.ru/conclusions?exploiter=%s&q=%s'
                 % (f['inn'], quote(slovo)))
            z = {'fakt_id': f['fakt_id'], 'inn': f['inn'], 'iskali': slovo, 'zapros': u,
                 'ts': time.strftime('%Y-%m-%d %H:%M:%S')}
            try:
                pg.goto(u, timeout=90000, wait_until='domcontentloaded')
                pg.wait_for_timeout(5500)
                html = pg.content()
                stroki = []
                for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S):
                    tekst = re.sub(r'\s+', ' ', _TEG.sub(' ', tr)).strip()
                    m = _NOM.search(tekst)
                    if m:
                        stroki.append({'nomer': m.group(0), 'tekst': tekst[:400]})
                z['strok_naydeno'] = len(stroki)
                # ОТБОР СТРОГИЙ. Первая версия сопоставляла цифры заводского номера с
                # ЛЮБЫМ местом строки — и «зав. № 407» совпал с цифрами внутри номера
                # заключения 26-ТУ-614407-2025, где объект вообще «Фонтанная арматура».
                # Это увидено глазами на восьми пробных фактах. Теперь два условия
                # ОДНОВРЕМЕННО, иначе честное «не нашли»:
                #   1) заводской номер стоит в описании ИМЕННО как «зав. № X»;
                #   2) в описании есть слово нашей номенклатуры.
                vybor = None
                for s in stroki:
                    op = _OPISANIE(s['tekst'])
                    if not NASHE.search(op.lower()):
                        continue
                    if zav and _norm_zav(zav) in _ZAV_SPISOK(op):
                        vybor = s
                        break
                if not vybor and stroki:
                    # без заводского номера — по совпадению слов описания с текстом факта,
                    # и только если описание про нашу машину
                    slova = set(re.findall(r'[А-Яа-яA-Za-z0-9]{4,}',
                                           (f.get('tekst') or '').lower()))
                    kand = [s for s in stroki if NASHE.search(_OPISANIE(s['tekst']).lower())]
                    if slova and kand:
                        luchshiy = max(kand, key=lambda s: len(
                            slova & set(re.findall(r'[А-Яа-яA-Za-z0-9]{4,}',
                                                   s['tekst'].lower()))))
                        sovpalo = len(slova & set(re.findall(
                            r'[А-Яа-яA-Za-z0-9]{4,}', luchshiy['tekst'].lower())))
                        # одно случайное слово ничего не доказывает
                        if sovpalo >= 3:
                            vybor = luchshiy
                            z['sovpalo_slov'] = sovpalo
                if vybor:
                    z['zaklyuchenie'] = vybor['nomer']
                    z['ssylka'] = 'https://monitor-pb.ru/conclusion/' + quote(vybor['nomer'])
                    z['stroka'] = vybor['tekst']
                    z['po_zavodskomu'] = bool(zav and _cifry(zav)
                                              and _cifry(zav) in _cifry(vybor['tekst']))
                    itog['nashli_zaklyuchenie'] += 1
                else:
                    itog['ne_nashli'] += 1
            except Exception as e:
                z['oshibka'] = str(e)[:150]
                itog['oshibki'].append('%s: %s' % (f['fakt_id'], str(e)[:80]))
            _zapisat(z)
        br.close()
    itog['oshibki'] = itog['oshibki'][:6]
    print(json.dumps(itog, ensure_ascii=False))


if __name__ == '__main__':
    main()
