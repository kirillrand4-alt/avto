"""Связка панели с работником проверки адресов на отдельном сервере.

Обмен идёт файлами через дроп, прямого доступа между машинами нет. Здесь
защищаются два правила:

  * хороним адрес ТОЛЬКО по вердикту «нет ящика». «Отказ пробе» и «неясно»
    очередь не трогают: это про работника (нет PTR, требуют TLS, серый
    список), а не про адрес. 07.08 по такому «коду» едва не выбросили четыре
    живых контакта;
  * публикуем только адреса БЕЗ вердикта — иначе работник каждые десять минут
    перепроверял бы всю очередь и жёг свой IP на пустом месте.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.addr_probe import ЕСТЬ, НЕТ_ЯЩИКА, ОТКАЗ_ПРОБЕ  # noqa: E402
from sender.probe_sync import ЗАДАНИЕ, РЕЗУЛЬТАТ, ProbeSync  # noqa: E402


class _Store:
    def __init__(self, письма, enabled=None):
        self.письма = письма
        self.enabled = enabled
        self.решения = []
        self.suppression = []
        self.настройки = {}

    def get_setting(self, key, default=None):
        return self.enabled if key == "probe_sync_enabled" else default

    def confirm_list(self, **kw):
        return list(self.письма)

    def confirm_decide(self, rid, **kw):
        self.решения.append((rid, kw.get("status"), kw.get("reason")))
        return True

    def suppression_add(self, entry):
        self.suppression.append((entry.scope, entry.value, entry.reason))
        return (1, True)

    def suppression_values(self, *, reason, scope="email"):
        return set()


class _Probe:
    def __init__(self, кэш=None, приговор=()):
        self.кэш = dict(кэш or {})
        # Адреса с приговором доставки: настоящий AddrProbe._save на них
        # отвечает False и запись пробы не пропускает.
        self.приговор = {(a or "").strip().lower() for a in приговор}
        self.записано = []

    def cached(self, email):
        з = self.кэш.get((email or "").strip().lower())
        return {"verdict": з} if з else None

    def _save(self, адрес, вердикт, код, ответ, mx):
        if адрес in self.приговор:
            return False
        self.кэш[адрес] = вердикт
        self.записано.append((адрес, вердикт))
        return True

    def verdict_emails(self, вердикт):
        return {a for a, v in self.кэш.items() if v == вердикт}


ПИСЬМА = [{"id": 1, "email": "zhivoy@zavod.ru", "kind": "outbound"},
          {"id": 2, "email": "myortvyy@zavod.ru", "kind": "outbound"},
          {"id": 3, "email": "otkaz@zavod.ru", "kind": "outbound"},
          {"id": 9, "email": "klient@zavod.ru", "kind": "reply"}]

ВЕРДИКТЫ = "\n".join(json.dumps(з, ensure_ascii=False) for з in [
    {"email": "zhivoy@zavod.ru", "verdict": ЕСТЬ, "code": 250, "answer": "OK"},
    {"email": "myortvyy@zavod.ru", "verdict": НЕТ_ЯЩИКА, "code": 550,
     "answer": "no such user"},
    {"email": "otkaz@zavod.ru", "verdict": ОТКАЗ_ПРОБЕ, "code": 550,
     "answer": "no PTR record for your host"},
])


def _синк(store, probe, ответы=None, ловушки=()):
    """ProbeSync с подменённым дропом: сеть в тестах не трогаем."""
    s = ProbeSync(store=store, probe=probe)
    s.положено = {}

    def _дроп(метод, имя, данные=None):
        if метод == "PUT":
            s.положено[имя] = данные
            return b"ok"
        if (ответы or {}).get(имя) is None:
            raise RuntimeError("на дропе такого файла нет")
        return (ответы or {})[имя].encode("utf-8")

    s._дроп = _дроп
    return s


# ---- приём вердиктов ---- #

def test_horonim_tolko_myortvyy_adres():
    store = _Store(ПИСЬМА)
    синк = _синк(store, _Probe(), ответы={РЕЗУЛЬТАТ: ВЕРДИКТЫ})
    итог = синк.забрать()
    assert итог["строк"] == 3 and итог["снято_писем"] == 1
    assert [r[0] for r in store.решения] == [2]
    assert store.suppression == [("email", "myortvyy@zavod.ru", "bounce_hard")]


def test_vse_verdikty_popadayut_v_kesh():
    """Даже «отказ пробе» пишется: иначе адрес публиковался бы вечно."""
    probe = _Probe()
    синк = _синк(_Store(ПИСЬМА), probe, ответы={РЕЗУЛЬТАТ: ВЕРДИКТЫ})
    итог = синк.забрать()
    assert итог["новых"] == 3
    assert dict(probe.записано) == {"zhivoy@zavod.ru": ЕСТЬ,
                                    "myortvyy@zavod.ru": НЕТ_ЯЩИКА,
                                    "otkaz@zavod.ru": ОТКАЗ_ПРОБЕ}


def test_prigovor_dostavki_silnee_otveta_rabotnika():
    """«Приму» от домена-catch-all не воскрешает адрес, который уже отбился.

    18.08: письмо на kk@vebfabrika.ru вернулось «invalid mailbox», а в 04:45
    работник спросил тот же сервер и получил 250 — домен принимает любой
    адрес. Запись пошла поверх приговора, и адрес вернулся в работу. Теперь
    AddrProbe._save её не пропускает, а приём обязан вести себя по приговору:
    иначе «есть» уедет в обогащение и снова выпустит адрес в отбор.
    """
    store = _Store(ПИСЬМА)
    probe = _Probe(кэш={"zhivoy@zavod.ru": НЕТ_ЯЩИКА},
                   приговор={"zhivoy@zavod.ru"})
    итог = _синк(store, probe, ответы={РЕЗУЛЬТАТ: ВЕРДИКТЫ}).забрать()
    assert итог["отклонено_поверх_приговора"] == 1
    assert итог["свод"].get(ЕСТЬ) is None, итог["свод"]
    assert итог["свод"].get(НЕТ_ЯЩИКА) == 2
    # письмо на похороненный адрес снято, адрес в стоп-листе
    assert sorted(r[0] for r in store.решения) == [1, 2]
    assert ("email", "zhivoy@zavod.ru", "bounce_hard") in store.suppression


def test_bityaya_stroka_ne_rvyot_priyom():
    store = _Store(ПИСЬМА)
    синк = _синк(store, _Probe(), ответы={РЕЗУЛЬТАТ: "{не json\n" + ВЕРДИКТЫ})
    assert синк.забрать()["снято_писем"] == 1


def test_pustoy_drop_ne_padaet():
    синк = _синк(_Store(ПИСЬМА), _Probe(), ответы={})
    итог = синк.забрать()
    assert итог["строк"] == 0 and "ошибка" in итог


# ---- публикация задания ---- #

def test_publikuem_tolko_bez_verdikta():
    probe = _Probe({"zhivoy@zavod.ru": ЕСТЬ})
    синк = _синк(_Store(ПИСЬМА), probe)
    итог = синк.опубликовать()
    assert итог["опубликовано"] == 2
    задание = json.loads(синк.положено[ЗАДАНИЕ].decode("utf-8"))
    assert sorted(задание) == ["myortvyy@zavod.ru", "otkaz@zavod.ru"]
    assert "klient@zavod.ru" not in задание       # ответы клиентов не проверяем


def test_nechego_publikovat_znachit_ne_hodim_na_drop():
    probe = _Probe({"zhivoy@zavod.ru": ЕСТЬ, "myortvyy@zavod.ru": НЕТ_ЯЩИКА,
                    "otkaz@zavod.ru": ОТКАЗ_ПРОБЕ})
    синк = _синк(_Store(ПИСЬМА), probe)
    assert синк.опубликовать()["опубликовано"] == 0
    assert синк.положено == {}


def test_partiya_ogranichena():
    письма = [{"id": i, "email": f"a{i}@z.ru", "kind": "outbound"}
              for i in range(50)]
    синк = _синк(_Store(письма), _Probe())
    синк.batch = 10
    assert синк.опубликовать()["опубликовано"] == 10


# ---- проход целиком ---- #

def test_tick_vklyuchyon_po_umolchaniyu():
    """Настройки нет — цикл работает: он ходит только на свой дроп."""
    синк = _синк(_Store(ПИСЬМА, enabled=None), _Probe(),
                 ответы={РЕЗУЛЬТАТ: ВЕРДИКТЫ})
    assert синк.enabled() is True
    итог = синк.tick()
    assert итог["принято"]["снято_писем"] == 1


def test_vyklyuchennyy_tsikl_nichego_ne_delaet():
    store = _Store(ПИСЬМА, enabled=False)
    синк = _синк(store, _Probe(), ответы={РЕЗУЛЬТАТ: ВЕРДИКТЫ})
    assert синк.tick() == {"ловушек": 0, "опубликовано": 0, "принято": {}}
    assert store.решения == []


def test_lovushki_snimayutsya_v_tom_zhe_prohode():
    письма = ПИСЬМА + [{"id": 5, "email": "abuse@zavod.ru", "kind": "outbound"}]
    store = _Store(письма)
    синк = _синк(store, _Probe(), ответы={РЕЗУЛЬТАТ: ВЕРДИКТЫ})
    итог = синк.tick()
    assert итог["ловушек"] == 1
    assert (5, "skipped") in [(r[0], r[1]) for r in store.решения]


def test_publikatsiya_ne_rvyot_tik_esli_drop_lyog():
    """Дроп не принял задание — приём вердиктов и заслон всё равно отработали.

    В очереди есть адрес, которого нет в вердиктах, — иначе публиковать нечего
    и падать негде.
    """
    письма = ПИСЬМА + [{"id": 6, "email": "novyy@zavod.ru", "kind": "outbound"}]
    store = _Store(письма)
    синк = _синк(store, _Probe(), ответы={РЕЗУЛЬТАТ: ВЕРДИКТЫ})

    def _падает(метод, имя, данные=None):
        if метод == "PUT":
            raise RuntimeError("дроп не отвечает")
        return ВЕРДИКТЫ.encode("utf-8")

    синк._дроп = _падает
    итог = синк.tick()
    assert итог["принято"]["снято_писем"] == 1
    assert "ошибка_публикации" in итог


# ---- ключи дропа ---- #

def test_klyuchi_iz_fayla_rannera(tmp_path, monkeypatch):
    """Служба панели не видит переменных раннера — читаем их файл.

    Первый живой прогон упёрся ровно сюда: ручной импорт работал (у процесса
    раннера ключи в окружении), а цикл службы отвечал «дроп не настроен».
    """
    monkeypatch.delenv("DROP_URL", raising=False)
    monkeypatch.delenv("DROP_TOKEN", raising=False)
    файл = tmp_path / "runner-secrets.env"
    файл.write_text('# комментарий\nDROP_URL=https://drop.example/drop\n'
                    'DROP_TOKEN="abc123"\nJOB_SECRET=не важно\n',
                    encoding="utf-8")
    s = ProbeSync(store=_Store(ПИСЬМА), probe=_Probe(),
                  secrets_file=str(файл))
    assert s._ключи() == ("https://drop.example/drop", "abc123")


def test_okruzhenie_vazhnee_fayla(tmp_path, monkeypatch):
    файл = tmp_path / "s.env"
    файл.write_text("DROP_URL=https://iz-fayla\nDROP_TOKEN=iz-fayla\n",
                    encoding="utf-8")
    monkeypatch.setenv("DROP_URL", "https://iz-okruzheniya")
    monkeypatch.setenv("DROP_TOKEN", "iz-okruzheniya")
    s = ProbeSync(store=_Store(ПИСЬМА), probe=_Probe(), secrets_file=str(файл))
    assert s._ключи() == ("https://iz-okruzheniya", "iz-okruzheniya")


def test_net_klyuchey_ponyatnaya_oshibka(tmp_path, monkeypatch):
    monkeypatch.delenv("DROP_URL", raising=False)
    monkeypatch.delenv("DROP_TOKEN", raising=False)
    s = ProbeSync(store=_Store(ПИСЬМА), probe=_Probe(),
                  secrets_file=str(tmp_path / "нет-такого.env"))
    with pytest.raises(RuntimeError, match="дроп не настроен"):
        s._дроп("GET", РЕЗУЛЬТАТ)


# ---- срочная проба адреса, введённого руками ---- #

def test_srochno_dopisyvaet_a_ne_podmenyaet_zadanie():
    """Срочный адрес встаёт ПЕРВЫМ, но не выбивает уже ждущие.

    Иначе один введённый руками адрес обнулял бы очередь на сотни писем.
    """
    синк = _синк(_Store(ПИСЬМА), _Probe(),
                 ответы={ЗАДАНИЕ: json.dumps(["staryy@zavod.ru",
                                              "vtoroy@zavod.ru"])})
    итог = синк.срочно(["Ruchnoy@Zavod.ru"])
    assert итог["срочных"] == 1
    задание = json.loads(синк.положено[ЗАДАНИЕ].decode("utf-8"))
    assert задание[0] == "ruchnoy@zavod.ru"
    assert set(задание) == {"ruchnoy@zavod.ru", "staryy@zavod.ru",
                            "vtoroy@zavod.ru"}


def test_srochno_budit_rabotnika_zadaniem():
    """Мало положить адрес в файл: работник должен узнать об этом сейчас."""
    синк = _синк(_Store(ПИСЬМА), _Probe(), ответы={})
    синк._подпись = lambda: "секрет"
    итог = синк.срочно(["ruchnoy@zavod.ru"])
    задачи = [и for и in синк.положено if и.startswith("vjob-")]
    assert len(задачи) == 1 and итог["работник_разбужен"] is True
    з = json.loads(синк.положено[задачи[0]].decode("utf-8"))
    assert з["task"] == "probe" and з.get("sig")


def test_srochno_ne_trogaet_uzhe_proverennyy():
    """Адрес с вердиктом переспрашивать незачем — это лишний след с IP."""
    синк = _синк(_Store(ПИСЬМА), _Probe({"znakomyy@zavod.ru": ЕСТЬ}),
                 ответы={})
    итог = синк.срочно(["znakomyy@zavod.ru"])
    assert итог == {"срочных": 0}
    assert синк.положено == {}


def test_srochno_perezhivaet_myortvyy_drop():
    """Работник недоступен — адрес всё равно записан в задание, а не потерян."""
    синк = _синк(_Store(ПИСЬМА), _Probe(), ответы={})

    def _тольконе(*a, **kw):
        raise RuntimeError("раннер лежит")

    синк._толкнуть = _тольконе
    итог = синк.срочно(["ruchnoy@zavod.ru"])
    assert итог["срочных"] == 1 and итог["работник_разбужен"] is False
    assert json.loads(синк.положено[ЗАДАНИЕ].decode("utf-8")) == \
        ["ruchnoy@zavod.ru"]


def test_priyom_ne_vozvrashchaet_galku_vseyadnomu_domenu():
    """Домен, принимающий любой адрес, не получает «есть» обратно.

    Файл вердиктов на дропе накопительный и перечитывается каждый круг. Без
    сверки с доменами разовая перепроверка обнулялась бы через десять минут.
    """
    from sender.addr_probe import ПРИНИМАЕТ_ВСЁ

    store = _Store(ПИСЬМА)
    синк = _синк(store, _Probe(), ответы={РЕЗУЛЬТАТ: ВЕРДИКТЫ})
    синк._domeny_prinimayut_vsyo = lambda: {"zavod.ru"}
    итог = синк.забрать()
    assert итог["свод"].get(ПРИНИМАЕТ_ВСЁ) == 1
    assert итог["свод"].get(ЕСТЬ) is None
    # «Нет ящика» знание о домене не отменяет: явный отказ сильнее.
    assert [r[0] for r in store.решения] == [2]
