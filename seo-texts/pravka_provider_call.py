# -*- coding: utf-8 -*-
"""Правка `C:\\sender\\server\\verify_company.py`: обходить мёртвый адрес шлюза.

ПОЧЕМУ. Имя `router.cheap` разъезжается на два адреса Cloudflare, и с сервера владельца
один из них непроходим: TCP-connect к нему УДАЁТСЯ (промежуточный фильтр отвечает SYN-ACK
за 0,02 с), а рвётся TLS-рукопожатие - `WinError 10054`. Штатный
`socket.create_connection` меняет адрес только при неудачном TCP-connect, поэтому до
живого второго адреса клиент не доходит никогда. Замеры - в `SHLYUZ-PROVAJDERA-OPIS.md`.

ЧТО ДЕЛАЕТ ПРАВКА. Добавляет перебор адресов, где ПРИГОДНОСТЬ АДРЕСА ПРОВЕРЯЕТСЯ
РУКОПОЖАТИЕМ, а не коннектом, с коротким таймаутом на адрес. Оба пути функции
`_provider_call_stdlib` переводятся на него:

    основной  `http.client.HTTPSConnection(host, timeout=240)` -> `_HTTPSPerebor(...)`
    фолбэк    `_BEZ_PROXY.open(req, ...)`                      -> `_SHLYUZ_OPENER.open(req, ...)`

ЧЕГО ПРАВКА НЕ ДЕЛАЕТ - намеренно:

  - НЕ меняет сигнатуру `_provider_call_stdlib(prompt, model=None)`. Её зовут
    `enrich_contacts.py` (строки 4850 и 6877, второй - с `model=`), `news_scan.py`
    (1112) и сам `verify_company.py` (405). Все вызовы продолжают работать без правок.
  - НЕ трогает общий `_BEZ_PROXY`. Он используется и для обхода чужих сайтов (строки 214
    и 575), и менять поведение всех этих путей ради шлюза - лишний риск. Для шлюза
    заводится ОТДЕЛЬНЫЙ опенер `_SHLYUZ_OPENER` с теми же настройками прокси (их нет).
  - НЕ кэширует адрес жёстко: живой адрес запоминается лишь как ПОДСКАЗКА порядка на 10
    минут. Он пробуется первым, но остальные остаются в переборе. Умрёт он - перебор
    просто уйдёт дальше, без ожидания протухания кэша.

ЯВНАЯ ОШИБКА ВМЕСТО ТИШИНЫ. Если рукопожатия не дал НИ ОДИН адрес, наружу идёт
`OSError` с перечислением ВСЕХ адресов и причины по каждому. Кроме того, у основного пути
стоял голый `except Exception: pass` - причина его падения терялась, и наружу уходила
ошибка фолбэка, то есть диагноз подменялся чужим. Теперь причина запоминается в
`_SBOY_OSNOVNOGO` и печатается, когда падают оба пути. Тип исключения при этом НЕ
подменяется: пересобрать чужой класс (тот же `HTTPError`) одной строкой нельзя, и попытка
сама стала бы новой поломкой.

Использование:
    python3 seo-texts/zapusk_na_servere.py pravka_provider_call.py --proverit
    python3 seo-texts/zapusk_na_servere.py pravka_provider_call.py --zamer
    python3 seo-texts/zapusk_na_servere.py pravka_provider_call.py --primenit --zamer
    python3 seo-texts/zapusk_na_servere.py pravka_provider_call.py --otkatit <файл.bak>
"""
import os
import py_compile
import shutil
import sys
import time

CEL = os.environ.get('VERIFY_COMPANY_PATH', r'C:\sender\server\verify_company.py')

# ------------------------------------------------------------------ якоря
A0_YAKOR = '_BEZ_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))'
A0_NOVOE = A0_YAKOR + '''

# --- обход мёртвого адреса шлюза (правка 17.09.2026) -------------------------------
# С этого сервера имя router.cheap разъезжается на два адреса Cloudflare, и один из них
# непроходим: TCP-connect удаётся (фильтр отвечает SYN-ACK за 0,02 с), а рвётся TLS -
# WinError 10054. Штатный create_connection меняет адрес ТОЛЬКО при неудачном connect,
# поэтому до живого адреса клиент не доходил никогда. Здесь пригодность адреса проверяется
# РУКОПОЖАТИЕМ и с коротким таймаутом на адрес.
import http.client as _hc_perebor  # noqa: E402
import socket as _sock_perebor  # noqa: E402
import ssl as _ssl_perebor  # noqa: E402

_TAJMAUT_NA_ADRES = 8.0          # столько ждём ОДИН адрес, а не весь бюджет вызова
_ZHIVOY_ADRES = {'adres': None, 'kogda': 0.0}   # подсказка порядка, НЕ кэш соединения
_SBOY_OSNOVNOGO = {'prichina': ''}              # почему упал основной путь (был голый pass)


def _soedinit_perebor(host, port=443, ctx=None, timeout=None,
                      na_adres=_TAJMAUT_NA_ADRES):
    """Сокет к первому адресу имени, который ДАЛ РУКОПОЖАТИЕ.

    Возвращает уже обёрнутый TLS-сокет. Если не смог ни один адрес - бросает OSError с
    перечислением всех адресов и причин: молчаливого отказа здесь быть не должно.
    """
    ctx = ctx or _ssl_perebor.create_default_context()
    adresa = _sock_perebor.getaddrinfo(host, port, 0, _sock_perebor.SOCK_STREAM)
    zh = _ZHIVOY_ADRES.get('adres')
    if zh and (time.time() - _ZHIVOY_ADRES.get('kogda', 0)) < 600:
        adresa = sorted(adresa, key=lambda x: 0 if x[4][0] == zh else 1)
    besy = []
    for af, tp, pr, _kan, sa in adresa:
        s = None
        try:
            s = _sock_perebor.socket(af, tp, pr)
            s.settimeout(na_adres)
            s.connect(sa)
            s = ctx.wrap_socket(s, server_hostname=host)
            s.settimeout(timeout)
            _ZHIVOY_ADRES['adres'] = sa[0]
            _ZHIVOY_ADRES['kogda'] = time.time()
            return s
        except Exception as ex:  # noqa: BLE001
            besy.append('%s -> %s' % (sa[0], type(ex).__name__))
            try:
                if s is not None:
                    s.close()
            except Exception:  # noqa: BLE001
                pass
    raise OSError('шлюз %s: TLS-рукопожатия не дал НИ ОДИН адрес (%s)'
                  % (host, '; '.join(besy) or 'адресов не нашлось'))


class _HTTPSPerebor(_hc_perebor.HTTPSConnection):
    """HTTPSConnection, у которого меняется ровно одно: как выбирается адрес."""

    def connect(self):
        if getattr(self, '_tunnel_host', None):
            # туннель через прокси нам не нужен, но если появится - отдаём штатному коду
            return _hc_perebor.HTTPSConnection.connect(self)
        t = self.timeout
        if t is _sock_perebor._GLOBAL_DEFAULT_TIMEOUT:
            t = None
        self.sock = _soedinit_perebor(self.host, self.port or 443,
                                      ctx=getattr(self, '_context', None), timeout=t)


class _HandlerPerebor(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_HTTPSPerebor, req, context=self._context)


# ОТДЕЛЬНЫЙ опенер только для шлюза: общий _BEZ_PROXY ходит и на чужие сайты, ему менять
# способ соединения незачем.
_SHLYUZ_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                             _HandlerPerebor())
# --- конец правки 17.09.2026 -------------------------------------------------------'''

A1_STAROE = '        cn = http.client.HTTPSConnection(host, timeout=240)'
A1_NOVOE = ('        # перебор адресов с проверкой рукопожатием (см. _soedinit_perebor)\n'
            '        cn = _HTTPSPerebor(host, timeout=240)')

A2_STAROE = '    with _BEZ_PROXY.open(req, timeout=240) as r:'
A2_NOVOE = '    with _SHLYUZ_OPENER.open(req, timeout=240) as r:'

A3_STAROE = """        finally:
            cn.close()
    except Exception:  # noqa: BLE001
        pass"""
A3_NOVOE = """        finally:
            cn.close()
    except Exception as _ex_osnovnogo:  # noqa: BLE001
        # Причина падения ОСНОВНОГО пути раньше терялась в голом pass, и наружу уходила
        # ошибка фолбэка - то есть диагноз подменялся чужим. Запоминаем и приписываем.
        _SBOY_OSNOVNOGO['prichina'] = '%s: %s' % (type(_ex_osnovnogo).__name__,
                                                  str(_ex_osnovnogo)[:140])"""

A4_STAROE = """    with _SHLYUZ_OPENER.open(req, timeout=240) as r:
        return _sse_collect(r)"""
A4_NOVOE = """    try:
        with _SHLYUZ_OPENER.open(req, timeout=240) as r:
            return _sse_collect(r)
    except Exception:  # noqa: BLE001
        # Упали ОБА пути. Наружу идёт ровно то же исключение того же типа (пересобирать
        # чужой класс нельзя: HTTPError, например, строкой не конструируется, и попытка
        # подменила бы настоящую ошибку своей). Добавляем только видимость: причина
        # основного пути обычно и есть настоящий диагноз, а раньше она молча терялась.
        if _SBOY_OSNOVNOGO.get('prichina'):
            print('[шлюз] оба пути упали; основной путь до этого: %s'
                  % _SBOY_OSNOVNOGO['prichina'], flush=True)
        raise"""

PRAVKI = [('A0 перебор адресов', A0_YAKOR, A0_NOVOE),
          ('A1 основной путь', A1_STAROE, A1_NOVOE),
          ('A2 фолбэк на свой опенер', A2_STAROE, A2_NOVOE),
          ('A3 причина основного пути', A3_STAROE, A3_NOVOE),
          ('A4 явная ошибка наружу', A4_STAROE, A4_NOVOE)]
# A4 опирается на текст, который появляется только после A2 - порядок применения важен.


def proverit(t, tiho=False):
    if not tiho:
        print('### ЯКОРЯ в %s (%d знаков)' % (CEL, len(t)))
    horosho = True
    vidno = t
    for imya, staroe, novoe in PRAVKI:
        n = vidno.count(staroe)
        if not tiho:
            print('  %-26s встречается %d раз' % (imya, n))
        if n != 1:
            horosho = False
            if not tiho:
                print('       ЯКОРЬ НЕ ОДИН - правка применена не будет')
        vidno = vidno.replace(staroe, novoe, 1)   # как если бы уже применили
    return horosho


def primenit():
    t = open(CEL, encoding='utf-8').read()
    if '_soedinit_perebor' in t:
        print('УЖЕ ПРОПАТЧЕНО: _soedinit_perebor в файле есть, второй раз не трогаю')
        return True
    if not proverit(t):
        print('ОТКАЗ: якоря не сошлись, файл не тронут')
        return False
    bak = '%s.bak-%d' % (CEL, int(time.time()))
    shutil.copy2(CEL, bak)
    for imya, staroe, novoe in PRAVKI:
        if t.count(staroe) != 1:
            shutil.copy2(bak, CEL)
            print('ОТКАЗ на шаге %s (встретился %d раз), откачено из %s'
                  % (imya, t.count(staroe), bak))
            return False
        t = t.replace(staroe, novoe, 1)
        print('  применено: %s' % imya)
    open(CEL, 'w', encoding='utf-8').write(t)
    try:
        py_compile.compile(CEL, doraise=True)
    except Exception as ex:  # noqa: BLE001
        shutil.copy2(bak, CEL)
        print('ОШИБКА КОМПИЛЯЦИИ, откатил из %s: %s' % (bak, ex))
        return False
    print('ГОТОВО. Бэкап: %s' % bak)
    return True


def otkatit(bak):
    if not os.path.exists(bak):
        print('нет файла %s' % bak)
        return False
    shutil.copy2(bak, CEL)
    py_compile.compile(CEL, doraise=True)
    print('откачено из %s' % bak)
    return True


ZAGOLOVKI = [
    'ОАО «Щекиноазот» ввело в эксплуатацию установку по производству метанола, '
    'инвестиции 20 млрд рублей',
    '«Норникель» объявил тендер на поставку центробежных компрессоров для завода',
    'СИБУР начал строительство газоперерабатывающего комплекса в Амурской области',
    'Находкинский завод минеральных удобрений начал строительство второй очереди',
    'ЕВРАЗ НТМК завершил модернизацию кислородно-компрессорной станции',
]


def zamer(imya='ЗАМЕР'):
    """Живая проверка: 5 вызовов штатным путём и 5 разборов новостей.

    Каждая половина меряется ДВАЖДЫ: при естественном порядке DNS (он плавает, поэтому сам
    по себе ничего не доказывает) и с ПРИНУДИТЕЛЬНО мёртвым адресом первым - вот это
    воспроизводимо и сравнимо между «до» и «после».
    """
    import socket
    sys.path.insert(0, r'C:\sender\server')
    import verify_company as VC
    import news_scan as NS
    est = hasattr(VC, '_soedinit_perebor')
    print('\n### %s (%s)' % (imya, 'ПОСЛЕ правки' if est else 'ДО правки'))

    nast = socket.getaddrinfo
    ai = nast('router.cheap', 443, socket.AF_INET, socket.SOCK_STREAM)
    print('  DNS сейчас первым отдаёт: %s' % ai[0][4][0])
    mertvyy = [x for x in ai if x[4][0].startswith('104.')]
    poryadok = sorted(ai, key=lambda x: 0 if x[4][0].startswith('104.') else 1)

    def podmena(*a, **k):
        return poryadok

    def progon(chto, podstavit):
        ok = 0
        for i in range(5):
            t0 = time.time()
            try:
                if podstavit:
                    socket.getaddrinfo = podmena
                if chto == 'klient':
                    out = VC._provider_call_stdlib('Ответь одним словом: работает')
                    vidno = repr((out or '')[:22])
                else:
                    r = NS.extract_event(ZAGOLOVKI[i], 'проба')
                    otk = isinstance(r, dict) and r.get('_otkaz')
                    vidno = ('ОТКАЗ: ' + str(otk)[:44]) if otk else (
                        'капекс' if (r or {}).get('is_capex') else 'не капекс')
                    if otk:
                        raise RuntimeError(str(otk)[:80])
                ok += 1
                print('     %d: %s за %.1f с' % (i + 1, vidno, time.time() - t0))
            except Exception as ex:  # noqa: BLE001
                print('     %d: СБОЙ за %.1f с: %s: %s'
                      % (i + 1, time.time() - t0, type(ex).__name__, str(ex)[:96]))
            finally:
                socket.getaddrinfo = nast
        return ok

    print('  -- 5 вызовов _provider_call_stdlib, естественный порядок DNS --')
    a1 = progon('klient', False)
    print('     прошло %d из 5' % a1)
    print('  -- 5 разборов news_scan.extract_event на реальных заголовках --')
    b1 = progon('novost', False)
    print('     прошло %d из 5' % b1)

    if not mertvyy:
        print('  -- адреса 104.* в выдаче DNS нет, принудительную пробу пропускаю --')
        return
    print('  -- ПРИНУДИТЕЛЬНО мёртвый адрес первым %s --' % [x[4][0] for x in poryadok])
    print('     5 вызовов _provider_call_stdlib:')
    a2 = progon('klient', True)
    print('     прошло %d из 5   <- главное число' % a2)
    print('     5 разборов extract_event:')
    b2 = progon('novost', True)
    print('     прошло %d из 5   <- главное число' % b2)
    print('  ИТОГ %s: клиент %d/5, новости %d/5 (при мёртвом адресе первым)'
          % (imya, a2, b2))


if __name__ == '__main__':
    a = sys.argv[1:] or ['--proverit']
    if '--otkatit' in a:
        sys.exit(0 if otkatit(a[a.index('--otkatit') + 1]) else 1)
    if '--proverit' in a:
        proverit(open(CEL, encoding='utf-8').read())
    if '--zamer' in a and '--primenit' not in a:
        zamer('ЗАМЕР ДО')
    if '--primenit' in a:
        if not primenit():
            sys.exit(1)
        if '--zamer' in a:
            zamer('ЗАМЕР ПОСЛЕ')
