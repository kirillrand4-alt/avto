# -*- coding: utf-8 -*-
"""Ускорение «Подтвердить отправку» (владелец 21.10: «делай» п.1–3).

Правки ТОЛЬКО по якорям, с бэкапом `<файл>.bak-uskorenie-<ts>`; якорь обязан
встречаться ровно 1 раз, иначе СТОП без единой правки. После записи .py —
py_compile, при сбое откат всех файлов этого прогона из бэкапов. Повторный
прогон идемпотентен: правка с уже стоящим маркером — «УЖЕ БЫЛО».

Режимы (первый аргумент):
  py           п.1 (кэш проверки ящиков на один запрос очереди),
               п.2 (кэш карт получателей, TTL 45 с + сброс при записи),
               п.3-бэк (ручка /confirm/counts)
  front-sverka собрать НЕТРОНУТЫЙ фронт во временную папку и сравнить с тем,
               что раздаёт служба (нет ли в исходниках чужих невыкаченных правок)
  front        п.3-фронт: client.ts + Layout.tsx, сборка vite во временную
               папку, бэкап C:\\sender\\web\\dist -> dist.bak-uskorenie-<ts>,
               докопирование новой сборки поверх (старые бандлы не удаляются)
  --otkat      снять все вставки обратной заменой (чужие правки целы),
               dist — из первого dist.bak-uskorenie-* (копированием поверх)
Службу НЕ перезапускает. Базы не трогает. Писем не шлёт.
Корень можно переопределить USKORENIE_KOREN (для сухой проверки в песочнице).
"""
import glob
import io
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import time

КОРЕНЬ = os.environ.get("USKORENIE_KOREN", r"C:\sender\sender")
DIST = os.environ.get("USKORENIE_DIST", r"C:\sender\web\dist")
WEB = os.path.join(КОРЕНЬ, "web")
TS = time.strftime("%Y%m%d-%H%M%S")
БЭК = ".bak-uskorenie-"
М = "УСКОРЕНИЕ-21.10"


def путь(*ч):
    return os.path.join(КОРЕНЬ, *ч)


APP = путь("api", "app.py")
CONFIRM = путь("confirm.py")
STORE = путь("store.py")
CLIENT = путь("web", "src", "api", "client.ts")
LAYOUT = путь("web", "src", "components", "Layout.tsx")

# ---------------------------------------------------------------- правки .py
ПРАВКИ_PY = [
    # ---- п.1: confirm.py — проверка ящика с кэшем на один запрос ----
    (CONFIRM, f"{М}/п1-mozhno", '''    def _fallback_mailbox(self, *, inn=None, prefer_mailbox=None,
                          prefer_division=None) -> Optional[str]:
''', f'''    def _mozhno_slat(self, mailbox_id, now, kesh=None) -> bool:
        """{М}/п1-mozhno: can_send_now(manual=True) с кэшем на ОДИН запрос.

        Показ очереди звал проверку ящика дважды на каждый ящик (45 штук) для
        КАЖДОГО письма страницы — 6 SQL на вызов, 26 тыс. запросов и 4 с на
        50 писем. Ответ от письма не зависит, поэтому внутри одного запроса
        /confirm/queue он считается один раз на ящик. kesh — словарь,
        созданный ручкой на этот запрос и умирающий вместе с ним; без kesh
        (approve, отправка, CLI) проверка честная, как раньше.
        """
        if kesh is None:
            return self._sender.can_send_now(mailbox_id, now=now, manual=True)
        if mailbox_id not in kesh:
            kesh[mailbox_id] = self._sender.can_send_now(
                mailbox_id, now=now, manual=True)
        return kesh[mailbox_id]

    def _fallback_mailbox(self, *, inn=None, prefer_mailbox=None,
                          prefer_division=None, kesh=None) -> Optional[str]:
'''),
    (CONFIRM, f"{М}/п1-ok", '''                return self._sender.can_send_now(mid, now=now, manual=True)
''', f'''                return self._mozhno_slat(mid, now, kesh)  # {М}/п1-ok
'''),
    (CONFIRM, f"{М}/п1-sendas", '''    def send_as(self, row: dict, *, prefer_division: Optional[str] = None) -> dict:
''', f'''    def send_as(self, row: dict, *, prefer_division: Optional[str] = None,
                kesh: Optional[dict] = None) -> dict:  # {М}/п1-sendas
'''),
    (CONFIRM, f"{М}/п1-chosen", '''        chosen = self._fallback_mailbox(inn=row.get("inn"),
                                        prefer_mailbox=manual,
                                        prefer_division=нужное)
''', f'''        chosen = self._fallback_mailbox(inn=row.get("inn"),
                                        prefer_mailbox=manual,
                                        prefer_division=нужное,
                                        kesh=kesh)  # {М}/п1-chosen
'''),
    (CONFIRM, f"{М}/п1-opts", '''                ok = self._sender.can_send_now(mb.mailbox_id, now=now, manual=True)
''', f'''                ok = self._mozhno_slat(mb.mailbox_id, now, kesh)  # {М}/п1-opts
'''),
    # ---- п.1: app.py — словарь-кэш создаётся на запрос очереди ----
    (APP, f"{М}/п1-app-arg", '''        except (TypeError, ValueError):
            _sa_напр = False
''', f'''        except (TypeError, ValueError):
            _sa_напр = False
        # {М}/п1-app-arg: проверка ящиков считается один раз на ЭТОТ запрос
        # (словарь живёт только здесь, между запросами не переносится).
        try:
            _кэш_арг = ({{"kesh": {{}}}} if "kesh" in _inspect.signature(
                deps.confirm.send_as).parameters else {{}})
        except (TypeError, ValueError, NameError):
            _кэш_арг = {{}}
'''),
    (APP, f"{М}/п1-app-call", '''                sa = (deps.confirm.send_as(r, prefer_division=напр or None)
                      if _sa_напр else deps.confirm.send_as(r))
''', f'''                sa = (deps.confirm.send_as(r, prefer_division=напр or None,
                                           **_кэш_арг)
                      if _sa_напр else deps.confirm.send_as(r, **_кэш_арг))  # {М}/п1-app-call
'''),
    # ---- п.3-бэк: app.py — лёгкая ручка счётчиков (ДО /confirm/{{rid}}) ----
    (APP, f"{М}/п3-counts", '''    @app.get("/confirm/groups")
''', f'''    @app.get("/confirm/counts")
    def confirm_counts_only(p: Principal = Depends(principal)):
        """{М}/п3-counts: только счётчики очереди — для бейджа в меню.

        Бейдж раньше звал /confirm/queue?limit=1 раз в минуту на каждой
        вкладке, а это полная сборка очереди (скоринг, карты получателей,
        значки) ради одного числа. Объявлена ДО `/confirm/{{rid}}`: иначе
        FastAPI разберёт «counts» как {{rid}}.
        """
        return {{"counts": deps.confirm.counts()}}

    @app.get("/confirm/groups")
'''),
    # ---- п.2: store.py — кэш карт получателей ----
    (STORE, f"{М}/п2-groups", '''    def recipient_groups(self) -> dict:
''', f'''    # {М}/п2-kesh: карты получателей для очереди (группы, почтовики)
    # строятся полным чтением recipients (77 тыс. строк, 0,2–1 с) и звались
    # на КАЖДЫЙ показ очереди/бейджа/выпадашки групп. Держим в памяти 45 с;
    # сброс — при записи получателей через Store (upsert/валидация) и при
    # смене отпечатка (COUNT, MAX(id)) — его меняет импорт из другого
    # процесса. Правка extra_json мимо Store (ai_quota) видна через ≤45 с.
    _КЭШ_ПОЛУЧАТЕЛЕЙ_TTL = 45.0

    def _kesh_poluchateley(self, имя, собрать):
        import time as _t
        лок = self.__dict__.setdefault("_kesh_pol_lock", threading.Lock())
        кэш = self.__dict__.setdefault("_kesh_pol", {{}})
        try:
            with self._lock:
                отпечаток = tuple(self._conn.execute(
                    "SELECT COUNT(*), MAX(id) FROM recipients").fetchone())
        except Exception:  # noqa: BLE001 - без отпечатка просто без кэша
            return собрать()
        сейчас = _t.monotonic()
        with лок:
            з = кэш.get(имя)
            if з is not None and з[1] == отпечаток \\
                    and сейчас - з[0] < self._КЭШ_ПОЛУЧАТЕЛЕЙ_TTL:
                return з[2]
        значение = собрать()
        with лок:
            кэш[имя] = (сейчас, отпечаток, значение)
        return значение

    def kesh_poluchateley_sbros(self) -> None:
        """Сбросить кэш карт получателей ({М}/п2-kesh)."""
        кэш = self.__dict__.get("_kesh_pol")
        if кэш:
            кэш.clear()

    def recipient_groups(self) -> dict:
        """Группы получателей (с кэшем {М}/п2-kesh) — см. _recipient_groups_bez_kesha."""
        return self._kesh_poluchateley("groups", self._recipient_groups_bez_kesha)

    def _recipient_groups_bez_kesha(self) -> dict:  # {М}/п2-groups
'''),
    (STORE, f"{М}/п2-mx", '''    def recipient_mx_map(self) -> dict:
''', f'''    def recipient_mx_map(self) -> dict:
        """Почтовики получателей (с кэшем {М}/п2-kesh) — см. _recipient_mx_map_bez_kesha."""
        return self._kesh_poluchateley("mx", self._recipient_mx_map_bez_kesha)

    def _recipient_mx_map_bez_kesha(self) -> dict:  # {М}/п2-mx
'''),
    (STORE, f"{М}/п2-sbros-upsert", '''        email, domain, inn = _normalize_recipient_identity(r.email, r.domain, r.inn)
        now_iso = _now_iso()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO recipients
''', f'''        email, domain, inn = _normalize_recipient_identity(r.email, r.domain, r.inn)
        now_iso = _now_iso()
        self.kesh_poluchateley_sbros()  # {М}/п2-sbros-upsert
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO recipients
'''),
    (STORE, f"{М}/п2-sbros-valid", '''            if cur.rowcount == 0:
                raise StoreError(f"recipient not found: {recipient_id}")
''', f'''            self.kesh_poluchateley_sbros()  # {М}/п2-sbros-valid
            if cur.rowcount == 0:
                raise StoreError(f"recipient not found: {{recipient_id}}")
'''),
]

ПРАВКИ_FRONT = [
    (CLIENT, f"{М}/п3-client", '''  confirmGet(id: number): Promise<ConfirmReview> {
''', f'''  // {М}/п3-client: только счётчики очереди — для бейджа в меню
  confirmCounts(): Promise<{{ counts: Record<string, number> }}> {{
    return req("GET", "/confirm/counts");
  }},
  confirmGet(id: number): Promise<ConfirmReview> {{
'''),
    (LAYOUT, f"{М}/п3-layout", '''    queryFn: () => api.confirmQueue({ limit: 1 }),
''', f'''    // {М}/п3-layout: лёгкая ручка счётчиков; пока служба не перезапущена и
    // ручки нет — по-старому, через очередь (бейдж не пропадает)
    queryFn: () => api.confirmCounts().catch(() => api.confirmQueue({{ limit: 1 }})),
'''),
]


def читать(п):
    with io.open(п, encoding="utf-8", newline="") as f:
        return f.read()


def писать(п, т):
    with io.open(п, "w", encoding="utf-8", newline="") as f:
        f.write(т)


def применить(правки, компилировать):
    """Все проверки якорей ДО записи; запись — с бэкапами; откат при сбое."""
    тексты, план = {}, []
    for ф, маркер, якорь, новое in правки:
        if ф not in тексты:
            if not os.path.exists(ф):
                print(f"СТОП: нет файла {ф}")
                return False
            тексты[ф] = читать(ф)
        т = тексты[ф]
        eol = "\r\n" if "\r\n" in т else "\n"
        я = якорь.replace("\n", eol)
        н = новое.replace("\n", eol)
        if маркер in т:
            print(f"  УЖЕ БЫЛО: {маркер}")
            continue
        n = т.count(я)
        if n != 1:
            print(f"СТОП: якорь {маркер} встречается {n} раз в {ф} — ничего не правлю")
            return False
        тексты[ф] = т.replace(я, н, 1)
        план.append((ф, маркер))
    if not план:
        print("  всё уже стоит, правок нет")
        return True
    файлы = sorted({ф for ф, _ in план})
    бэкапы = {}
    try:
        for ф in файлы:
            б = ф + БЭК + TS
            shutil.copy2(ф, б)
            бэкапы[ф] = б
            print(f"  бэкап: {б}")
        for ф in файлы:
            писать(ф, тексты[ф])
        if компилировать:
            for ф in файлы:
                py_compile.compile(ф, doraise=True)
                print(f"  py_compile OK: {os.path.relpath(ф, КОРЕНЬ)}")
    except Exception as e:  # noqa: BLE001
        print(f"СБОЙ: {e!r} — откатываю этот прогон")
        for ф, б in бэкапы.items():
            shutil.copy2(б, ф)
            print(f"  откат: {ф}")
        return False
    for ф, маркер in план:
        print(f"  ПРАВКА: {маркер}  ({os.path.relpath(ф, КОРЕНЬ)})")
    return True


def ссылки(dist):
    ih = os.path.join(dist, "index.html")
    if not os.path.exists(ih):
        return None, ["нет index.html"]
    html = читать(ih)
    refs = sorted(set(re.findall(r"/assets/[A-Za-z0-9._-]+", html)))
    плохие = [r for r in refs if not os.path.exists(
        os.path.join(dist, r.lstrip("/").replace("/", os.sep)))]
    return refs, плохие


def собрать(out):
    if not os.path.isdir(os.path.join(WEB, "node_modules")):
        print("СТОП: нет web/node_modules — собрать на сервере нельзя")
        return False
    cmd = f'npx vite build --outDir "{out}" --emptyOutDir'
    t0 = time.time()
    р = subprocess.run(cmd, cwd=WEB, shell=True, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=600)
    хвост = (р.stdout or "")[-1500:] + (р.stderr or "")[-1500:]
    print(f"  vite build rc={р.returncode} за {time.time()-t0:.0f} с")
    if р.returncode != 0:
        print(хвост)
        return False
    refs, плохие = ссылки(out)
    if not refs or плохие:
        print("  сборка без index.html или с битыми ссылками:", плохие)
        return False
    return True


def front_sverka():
    tmp = tempfile.mkdtemp(prefix="uskorenie-sverka-")
    if not собрать(tmp):
        return
    новые, _ = ссылки(tmp)
    живые, _ = ссылки(DIST)
    print("  сборка нетронутых исходников:", новые)
    print("  раздаётся службой сейчас:   ", живые)
    print("  СОВПАДАЕТ" if новые == живые else
          "  НЕ СОВПАДАЕТ — в исходниках есть изменения, которых нет в dist")
    shutil.rmtree(tmp, ignore_errors=True)


def front():
    if not применить(ПРАВКИ_FRONT, компилировать=False):
        return
    tmp = tempfile.mkdtemp(prefix="uskorenie-front-")
    if not собрать(tmp):
        print("СБОЙ сборки — откатываю client.ts/Layout.tsx")
        for ф in (CLIENT, LAYOUT):
            б = ф + БЭК + TS
            if os.path.exists(б):
                shutil.copy2(б, ф)
                print(f"  откат: {ф}")
        return
    бэк = DIST + БЭК + TS
    shutil.copytree(DIST, бэк)
    print(f"  бэкап dist: {бэк}")
    shutil.copytree(tmp, DIST, dirs_exist_ok=True)
    refs, плохие = ссылки(DIST)
    if плохие:
        shutil.copy2(os.path.join(бэк, "index.html"), os.path.join(DIST, "index.html"))
        print("  ссылки битые -> index.html откачен:", плохие)
        return
    print("  dist обновлён, ссылки целы:", refs)
    shutil.rmtree(tmp, ignore_errors=True)


def otkat():
    """Обратная замена: каждый вставленный блок -> исходный якорь. Чужие правки
    в тех же файлах (соседняя сессия) при этом сохраняются — бэкап целиком
    не накатываем."""
    тексты = {}
    for ф, маркер, якорь, новое in ПРАВКИ_PY + ПРАВКИ_FRONT:
        if not os.path.exists(ф):
            continue
        т = тексты.get(ф) or читать(ф)
        eol = "\r\n" if "\r\n" in т else "\n"
        я, н = якорь.replace("\n", eol), новое.replace("\n", eol)
        if т.count(н) == 1:
            т = т.replace(н, я, 1)
            print(f"  снято: {маркер}")
        elif маркер in т:
            print(f"СТОП: {маркер} стоит, но блок изменён — откатите из "
                  f"{os.path.basename(ф)}{БЭК}* вручную")
            return
        тексты[ф] = т
    for ф, т in тексты.items():
        if т != читать(ф):
            shutil.copy2(ф, ф + ".bak-otkat-" + TS)
            писать(ф, т)
            if ф.endswith(".py"):
                py_compile.compile(ф, doraise=True)
            print(f"  записан {os.path.relpath(ф, КОРЕНЬ)}")
    бб = sorted(glob.glob(DIST + БЭК + "*"))
    if бб:
        shutil.copytree(бб[0], DIST, dirs_exist_ok=True)
        print(f"  dist <- {os.path.basename(бб[0])} (копированием поверх)")
    print("  ОТКАТ СДЕЛАН — нужен Restart-Service SenderPanel -Force")


def main():
    режим = sys.argv[1] if len(sys.argv) > 1 else ""
    print(f"корень: {КОРЕНЬ}  режим: {режим or '(не задан)'}")
    if режим == "--otkat":
        otkat()
    elif режим == "py":
        применить(ПРАВКИ_PY, компилировать=True)
    elif режим == "front-sverka":
        front_sverka()
    elif режим == "front":
        front()
    else:
        print(__doc__)
    print("=== ГОТОВО ===")


if __name__ == "__main__":
    main()
