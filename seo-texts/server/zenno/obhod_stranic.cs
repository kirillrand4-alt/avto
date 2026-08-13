// Кубик ZennoPoster 7.9: обход САЙТОВ пачкой в ОДНОМ инстансе.
//
// Зачем: дельфин поднимает профиль на КАЖДУЮ страницу (10-30 с) и по факту доходит только
// до главной. Зенка держит инстанс и проходит сайт целиком: главная -> карта сайта ->
// контакты -> второй уровень. Замер 12.08: 100 адресов по 9,7 с каждый.
//
// ПАЧКОЙ (владелец 13.08: «он запускает всё равно на 1 сайт 1 профиль?», «и этим глушит
// процессор»). ZennoPoster поднимает браузер на КАЖДОЕ выполнение шаблона, и при одной
// компании за выполнение процессор уходит на пересоздание инстансов, а не на работу.
// Поэтому кубик берёт из очереди подряд KOMPANIY_ZA_RAZ компаний и обходит их в одном
// браузере, очищая куки и кэш между ними. Восемь потоков по десять компаний — это восемь
// браузеров на восемьдесят сайтов вместо восьмидесяти браузеров.
//
// Ограничения 7.9, проверены на сервере (не менять на «привычное»):
//   * LoadProfile и DocumentText НЕ работают -> HTML берём FindElementByTag("html",0)
//     и GetAttribute("outerhtml");
//   * общий замок для файлов и списков — SyncObjects.ListSyncer.
//
// НАСТРАИВАТЬ В ПРОЕКТЕ НИЧЕГО НЕ НАДО: папки, очередь и прокси кубик находит сам.
// Списки sajty/proxy и переменные проекта используются, только если они уже заведены.
// От оператора — число потоков и повтор выполнения.
//
// ПАПКА ОБМЕНА (создаётся сама): C:\seostat\drop\zenno
//   ochered.txt      — очередь «ИНН;адрес», наполняет zenno_most.py --ochered
//   proxy.txt        — обычные прокси построчно (нет файла -> идём напрямую)
//   proxy_mobile.txt — МОБИЛЬНЫЕ: на них переходим, когда сайт не дался с обычного
//   gotovo\          — результат, эту папку слушает zenno_most.py --priyom
//   ne_otkrylis.txt  — что не далось даже с мобильного
//
// ВЫХОД (на компанию): <ИНН>_0.html ... + <ИНН>.urls.txt (адреса в том же порядке)
// и <ИНН>.err.txt при ошибках. JSON не собираем: экранировать HTML в C# руками —
// источник битых файлов.

// БЕЗ BOM. System.Text.Encoding.UTF8 в .NET пишет метку порядка байтов, и она
// приезжает в НАЧАЛО первой строки .urls.txt: питон читает адрес как "\ufeffhttp://..."
// и страница теряет привязку. Поймано на первой же партии (13.08).
var bez_bom = new System.Text.UTF8Encoding(false);

// --- настройки: переменная проекта, если заведена, иначе умолчание ---
Func<string, string, string> nastroyka = delegate(string imya, string po_umolchaniyu)
{
    try
    {
        string v = project.Variables[imya].Value;
        if (!string.IsNullOrEmpty(v)) return v;
    }
    catch { }        // переменной в проекте нет — штатный случай, не ошибка
    return po_umolchaniyu;
};

string koren_obmena = nastroyka("papka_obmena", @"C:\seostat\drop\zenno");
string papka = nastroyka("papka_vyhod", System.IO.Path.Combine(koren_obmena, "gotovo"));
string fajl_ocheredi = nastroyka("fajl_ocheredi",
                                 System.IO.Path.Combine(koren_obmena, "ochered.txt"));
string fajl_proxy = nastroyka("fajl_proxy",
                              System.IO.Path.Combine(koren_obmena, "proxy.txt"));
string fajl_proxy_mob = nastroyka("fajl_proxy_mobile",
                                  System.IO.Path.Combine(koren_obmena, "proxy_mobile.txt"));
System.IO.Directory.CreateDirectory(koren_obmena);
System.IO.Directory.CreateDirectory(papka);
if (!System.IO.File.Exists(fajl_ocheredi))
    System.IO.File.WriteAllText(fajl_ocheredi, "", bez_bom);

int predel = 3;
// Сколько внутренних страниц брать. Было 3 (владелец 13.08: «страниц написано много
// где 4, это какое-то ограничение?» — да, 3 внутренних плюс главная). Питоновский
// краул берёт до 10 и добирает второй уровень, поэтому поднимаем до 6: Зенка должна
// быть не хуже дельфина, а лучше. Чтобы глубина не съела скорость, ниже стоит
// правило остановки — набрали контакты, дальше не копаем.
if (!int.TryParse(nastroyka("stranic_max", "6"), out predel) || predel <= 0) predel = 6;
int za_raz = 10;
if (!int.TryParse(nastroyka("kompaniy_za_raz", "10"), out za_raz) || za_raz <= 0) za_raz = 10;

// --- прокси: читаем оба файла один раз на выполнение ---
Func<string, List<string>> chitat_proxy = delegate(string put)
{
    var l = new List<string>();
    try
    {
        if (System.IO.File.Exists(put))
            foreach (string s in System.IO.File.ReadAllLines(put))
                if (s.Trim().Length > 0 && !s.Trim().StartsWith("#")) l.Add(s.Trim());
    }
    catch { }
    return l;
};
var proxy_obychnye = chitat_proxy(fajl_proxy);
var proxy_mobilnye = chitat_proxy(fajl_proxy_mob);
try
{
    if (proxy_obychnye.Count == 0 && project.Lists["proxy"].Count > 0)
        foreach (string s in project.Lists["proxy"]) if (s.Trim().Length > 0)
            proxy_obychnye.Add(s.Trim());
}
catch { }
var sluchay = new Random(Guid.NewGuid().GetHashCode());


// --- ОТПЕЧАТОК: User-Agent и что ещё позволит сборка -------------------------------
// Владелец 13.08: «ua куки и всё остальное подставляются в новом кубике?» — честно:
// раньше нет. Кубик ставил только прокси и чистил куки, отпечаток был дефолтный, и
// в этом дельфин был сильнее (он подменял canvas, WebGL, WebRTC, часовой пояс).
//
// Методы у ZennoPoster 7.9 отличаются от документации (LoadProfile и DocumentText,
// например, не работают вовсе), поэтому вызываем через рефлексию: есть метод —
// используем, нет — молча пропускаем. Гадать вслепую тут дороже, чем проверить.
var ua_spisok = new string[] {
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 YaBrowser/25.6.0.0 Yowser/2.5 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
};

Func<string, object[], bool> vyzvat = delegate(string imya, object[] args)
{
    try
    {
        var tipy = new Type[args.Length];
        for (int i = 0; i < args.Length; i++) tipy[i] = args[i].GetType();
        var mi = instance.GetType().GetMethod(imya, tipy);
        if (mi == null) return false;
        mi.Invoke(instance, args);
        return true;
    }
    catch { return false; }
};

// один раз за выполнение показываем, что сборка вообще умеет — по этому списку
// решим, что ещё можно вшить (экран, язык, WebGL) вместо догадок
bool diagnostika = nastroyka("diagnostika_instansa", "1") == "1";
if (diagnostika)
{
    var imena = new List<string>();
    try
    {
        foreach (var m in instance.GetType().GetMethods())
        {
            string n = m.Name;
            if ((n.StartsWith("Set") || n.Contains("Agent") || n.Contains("Profile")
                 || n.Contains("Finger") || n.Contains("Screen") || n.Contains("Lang"))
                && !imena.Contains(n)) imena.Add(n);
        }
    }
    catch { }
    project.SendInfoToLog("инстанс умеет: " + string.Join(", ", imena.ToArray()), true);
}

// --- взять следующее задание из очереди (атомарно для всех потоков) ---
Func<string> sleduyushchee = delegate()
{
    string s = "";
    lock (SyncObjects.ListSyncer)
    {
        bool iz_spiska = false;
        try
        {
            if (project.Lists["sajty"].Count > 0)
            {
                s = project.Lists["sajty"][0];
                project.Lists["sajty"].RemoveAt(0);
                iz_spiska = true;
            }
        }
        catch { }    // списка sajty нет — работаем прямо с файлом
        if (!iz_spiska)
        {
            try
            {
                var vse = System.IO.File.ReadAllLines(fajl_ocheredi, bez_bom);
                int pervaya = -1;
                for (int i = 0; i < vse.Length; i++)
                    if (vse[i].Trim().Length > 0) { pervaya = i; break; }
                if (pervaya >= 0)
                {
                    s = vse[pervaya].Trim();
                    var ostatok = new List<string>();
                    for (int i = 0; i < vse.Length; i++)
                        if (i != pervaya && vse[i].Trim().Length > 0) ostatok.Add(vse[i]);
                    System.IO.File.WriteAllLines(fajl_ocheredi, ostatok.ToArray(),
                                                 bez_bom);
                }
            }
            catch (Exception e)
            {
                project.SendWarningToLog("очередь недоступна: " + e.Message, true);
            }
        }
    }
    return s;
};

string inn = "";
var oshibki = new System.Text.StringBuilder();

// Открыть адрес и вернуть HTML. Пустая строка = не открылось.
Func<string, string> vzyat = delegate(string adres)
{
    try
    {
        instance.ActiveTab.Navigate(adres, "");
        instance.ActiveTab.WaitDownloading();
        var he = instance.ActiveTab.FindElementByTag("html", 0);
        if (he == null || he.IsVoid)
        {
            oshibki.AppendLine(adres + " -> пустой документ");
            return "";
        }
        return he.GetAttribute("outerhtml");
    }
    catch (Exception e)
    {
        oshibki.AppendLine(adres + " -> " + e.Message);
        return "";
    }
};

// Почему страница не годится (пусто = годится). Отдельной функцией, а не флагом:
// причину надо видеть в логе — «429» и «капча» лечатся по-разному.
Func<string, string> pochemu_ne_godna = delegate(string h)
{
    if (h == null || h.Length < 600) return "пусто/обрывок";
    string n = h.ToLower();
    // 429 — ЛИМИТ ЗАПРОСОВ НА АДРЕС (владелец 13.08 увидел его в инстансе:
    // «почти 100% что это блок по прокси»). Страница длинная и осмысленная,
    // поэтому прежняя проверка по длине её пропускала как годную, и мобильный
    // повтор не запускался. Ловим по тексту: HTTP-код из ZennoPoster брать
    // ненадёжно, а формулировка у всех одна.
    if (n.Contains("too many requests") || n.Contains("слишком много запросов")
        || n.Contains("rate limit") || n.Contains("превышен лимит запросов")
        || (n.Contains("429") && n.Contains("request"))) return "429 лимит на адрес";
    if (n.Contains("just a moment") || n.Contains("checking your browser")) return "cloudflare";
    if (n.Contains("proxy authentication required")) return "прокси не пустил";
    if (n.Contains("доступ ограничен") || n.Contains("are you not a robot")
        || n.Contains("подтвердите, что вы человек")) return "антибот";
    if (n.Contains("403 forbidden") && h.Length < 3000) return "403";
    return "";
};
Func<string, bool> godnaya = delegate(string h)
{
    return pochemu_ne_godna(h).Length == 0;
};


// --- РЕШЕНИЕ КАПЧ (владелец 13.08: «и капмонстр и рукаптча и 2 каптча подключены,
// включи чтобы решались все виды капч»). Дельфин это умел через CapMonster, и пока
// кубик капчу просто отбрасывал, Зенка была слабее его на заслонённых сайтах.
//
// Как устроено: определяем тип по разметке, вытаскиваем sitekey, отдаём сервису с
// нужным method, полученный токен внедряем в страницу и ждём перезагрузку.
// Модули перебираем по очереди — какой из трёх ответит, тот и решает. Имена dll
// зависят от установки ZennoPoster, поэтому вынесены в переменную kapcha_moduli.
var moduli = new List<string>();
foreach (string m in nastroyka("kapcha_moduli",
         "CapMonster2.dll,RuCaptcha.dll,2Captcha.dll,AntiCaptcha.dll").Split(','))
    if (m.Trim().Length > 0) moduli.Add(m.Trim());

// (тип, sitekey) со страницы; тип пустой -> капчи нет
Func<string, string[]> opoznat_kapchu = delegate(string h)
{
    if (h == null || h.Length == 0) return new string[] { "", "" };
    string n = h.ToLower();
    string tip = "";
    if (n.Contains("cf-turnstile") || n.Contains("challenges.cloudflare.com")
        || n.Contains("just a moment")) tip = "turnstile";
    else if (n.Contains("smartcaptcha") || n.Contains("captcha-api.yandex")) tip = "yandex";
    else if (n.Contains("g-recaptcha") || n.Contains("recaptcha/api.js")) tip = "recaptcha";
    if (tip.Length == 0) return new string[] { "", "" };
    var m = System.Text.RegularExpressions.Regex.Match(h,
        "(?:data-sitekey|sitekey)[\"'\\s:=]+([A-Za-z0-9_\\-]{8,})",
        System.Text.RegularExpressions.RegexOptions.IgnoreCase);
    return new string[] { tip, m.Success ? m.Groups[1].Value : "" };
};

// Решить и внедрить токен. true — страница после этого открылась.
Func<string, string, string, bool> reshit_kapchu = delegate(string tip, string kluch, string adres)
{
    if (kluch.Length == 0) return false;
    string metod = tip == "turnstile" ? "turnstile"
                 : (tip == "yandex" ? "yandex" : "userrecaptcha");
    string parametry = "pageurl=" + adres + "\r\nmethod=" + metod;
    string token = "";
    foreach (string modul in moduli)
    {
        try
        {
            token = ZennoPoster.CaptchaRecognition(modul, kluch, parametry);
        }
        catch (Exception e)
        {
            oshibki.AppendLine("капча " + modul + ": " + e.Message);
            token = "";
        }
        if (!string.IsNullOrEmpty(token) && token.Length > 20) break;
    }
    if (string.IsNullOrEmpty(token) || token.Length <= 20) return false;

    // внедряем токен в поле, которое ждёт именно этот тип капчи, и пробуем
    // отправить форму: у части сайтов колбэк вызывается сам, у части — нет
    string js;
    if (tip == "turnstile")
        js = "var e=document.querySelector('[name=\"cf-turnstile-response\"]');"
           + "if(e){e.value='" + token + "';}"
           + "var f=document.forms[0]; if(f){try{f.submit();}catch(x){}}";
    else if (tip == "yandex")
        js = "var e=document.querySelector('[name=\"smart-token\"]');"
           + "if(e){e.value='" + token + "';}"
           + "var f=document.forms[0]; if(f){try{f.submit();}catch(x){}}";
    else
        js = "var e=document.getElementById('g-recaptcha-response');"
           + "if(e){e.innerHTML='" + token + "'; e.value='" + token + "';}"
           + "try{if(typeof ___grecaptcha_cfg!=='undefined'){"
           + "for(var k in ___grecaptcha_cfg.clients){var c=___grecaptcha_cfg.clients[k];"
           + "for(var p in c){var o=c[p];if(o&&o.callback){o.callback('" + token + "');}}}}}"
           + "catch(x){}"
           + "var f=document.forms[0]; if(f){try{f.submit();}catch(x){}}";
    try
    {
        instance.ActiveTab.MainDocument.EvaluateScript(js);
        instance.ActiveTab.WaitDownloading();
    }
    catch (Exception e)
    {
        oshibki.AppendLine("внедрение токена: " + e.Message);
        return false;
    }
    return true;
};

// Карта сайта: robots.txt -> Sitemap, иначе /sitemap.xml. Питон её здесь не добудет —
// сайт закрыт как раз для него, поэтому карту берём тем же браузером.
Func<string, List<string>> iz_karty = delegate(string koren)
{
    var naydeno = new List<string>();
    var karty = new List<string>();
    string rob = vzyat(koren + "/robots.txt");
    if (rob.Length > 0)
        foreach (System.Text.RegularExpressions.Match m in
                 System.Text.RegularExpressions.Regex.Matches(rob, "Sitemap:\\s*(\\S+)",
                     System.Text.RegularExpressions.RegexOptions.IgnoreCase))
        {
            string s = m.Groups[1].Value.Trim();
            if (s.StartsWith("http") && !karty.Contains(s)) karty.Add(s);
        }
    if (karty.Count == 0) karty.Add(koren + "/sitemap.xml");

    var slova_k = new string[] { "contact", "kontakt", "svyaz", "about", "o-kompanii",
                                 "o-nas", "rukovod", "staff", "team", "sotrudnik" };
    int razobrano = 0;
    for (int k = 0; k < karty.Count && razobrano < 3 && naydeno.Count < 6; k++)
    {
        string xml = vzyat(karty[k]);
        razobrano++;
        if (xml.Length == 0) continue;
        foreach (System.Text.RegularExpressions.Match m in
                 System.Text.RegularExpressions.Regex.Matches(xml, "<loc>([^<]{1,300})</loc>",
                     System.Text.RegularExpressions.RegexOptions.IgnoreCase))
        {
            string loc = m.Groups[1].Value.Trim();
            string nl = loc.ToLower();
            if (nl.EndsWith(".xml") && !karty.Contains(loc) && karty.Count < 5)
            {
                karty.Add(loc);      // карта карт
                continue;
            }
            bool nuzhna = false;
            foreach (string s in slova_k) if (nl.Contains(s)) { nuzhna = true; break; }
            if (nuzhna && !naydeno.Contains(loc) && naydeno.Count < 6) naydeno.Add(loc);
        }
    }
    return naydeno;
};

// Почты на собранных страницах: по ним работает правило остановки. Тот же принцип,
// что в питоне («не первые N страниц, а пока приносят новые контакты»).
var re_pochta = new System.Text.RegularExpressions.Regex(
    "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,6}");
Func<string, HashSet<string>> pochty_so_stranicy = delegate(string h)
{
    var n = new HashSet<string>();
    foreach (System.Text.RegularExpressions.Match m in re_pochta.Matches(h ?? ""))
    {
        string e = m.Value.ToLower();
        if (e.EndsWith(".png") || e.EndsWith(".jpg") || e.EndsWith(".gif")
            || e.EndsWith(".webp") || e.EndsWith(".svg")) continue;
        n.Add(e);
    }
    return n;
};

var slova = new string[] { "contact", "kontakt", "svyaz", "about", "o-kompanii",
                           "o-nas", "company", "rukovod", "staff", "team",
                           "sotrudnik", "rekvizit" };
var ugadki = new string[] { "/contacts/", "/kontakty/", "/contact/", "/about/",
                            "/o-kompanii/", "/company/staff/", "/company/", "/rukovodstvo/" };
var re = new System.Text.RegularExpressions.Regex(
    "href\\s*=\\s*[\"']([^\"'#]{1,180})[\"']",
    System.Text.RegularExpressions.RegexOptions.IgnoreCase);

int vsego_stranic = 0, vsego_kompaniy = 0, s_mobilki = 0, s_kapchey = 0,
    s_drugim_proxy = 0, s_pauzoy = 0;

for (int nomer = 0; nomer < za_raz; nomer++)
{
    string stroka = sleduyushchee();
    // ЖДЁМ, А НЕ УМИРАЕМ (владелец 13.08: «пока он стоит — очередь копится, но не
    // разбирается»). Раньше пустая очередь сразу гасила поток, и шаблон с конечным
    // числом выполнений выгорал вхолостую за секунды, пока мост доливал задания.
    // Теперь ждём до трёх минут, проверяя раз в 15 секунд: наполнение очереди идёт
    // каждые две минуты, так что поток переживает паузу и подхватывает новое сам.
    if (stroka.Length == 0)
    {
        for (int ozhid = 0; ozhid < 12 && stroka.Length == 0; ozhid++)
        {
            System.Threading.Thread.Sleep(15000);
            stroka = sleduyushchee();
        }
    }
    if (stroka.Length == 0)
    {
        project.SendInfoToLog("очередь пуста три минуты — поток завершён", true);
        break;
    }
    var chasti = stroka.Split(';');
    inn = chasti[0].Trim();
    string url = (chasti.Length > 1 ? chasti[1] : chasti[0]).Trim();
    if (url.Length == 0) continue;
    if (!url.StartsWith("http")) url = "http://" + url;
    oshibki.Length = 0;

    // между компаниями чистим сессию, меняем адрес выхода и отпечаток
    instance.ClearCookie();
    instance.ClearCache();
    string ua = ua_spisok[sluchay.Next(ua_spisok.Length)];
    if (!vyzvat("SetUserAgent", new object[] { ua }))
        vyzvat("SetHeader", new object[] { "User-Agent", ua });
    if (proxy_obychnye.Count > 0)
        instance.SetProxy(proxy_obychnye[sluchay.Next(proxy_obychnye.Count)]);

    var adresa = new List<string>();
    var htmly = new List<string>();
    string kanal = "обычный";     // каким выходом реально взяли сайт

    string glavnaya = vzyat(url);
    // ПОВТОР С МОБИЛЬНОГО (владелец 13.08). Датацентр-адреса режут не только справочники:
    // часть корпоративных сайтов сидит за антиботом, который пропускает мобильную сеть и
    // молча отдаёт пустоту всем остальным. Пробуем ровно один раз и только при провале —
    // мобильных адресов мало и они платные.
    string prichina = pochemu_ne_godna(glavnaya);
    if (prichina.Length > 0)
    {
        project.SendInfoToLog(inn + ": " + prichina + " -> пробуем иначе, " + url, true);
        // 429 — это лимит именно на адрес выхода, поэтому первый повтор дешёвый:
        // другой обычный прокси. Мобильные бережём, их три штуки.
        if (prichina.StartsWith("429"))
        {
            // лимит на адрес часто снимается сам через несколько секунд — это
            // дешевле смены выхода, поэтому сперва короткая пауза на том же прокси
            System.Threading.Thread.Sleep(4000);
            string povtor = vzyat(url);
            if (godnaya(povtor)) { glavnaya = povtor; kanal = "пауза"; s_pauzoy++; }
            else if (proxy_obychnye.Count > 1)
            {
                instance.SetProxy(proxy_obychnye[sluchay.Next(proxy_obychnye.Count)]);
                instance.ClearCookie();
                string drugoy = vzyat(url);
                if (godnaya(drugoy)) { glavnaya = drugoy; kanal = "смена прокси"; s_drugim_proxy++; }
            }
        }
        if (!godnaya(glavnaya) && proxy_mobilnye.Count > 0)
        {
            instance.SetProxy(proxy_mobilnye[sluchay.Next(proxy_mobilnye.Count)]);
            instance.ClearCookie();
            string vtoraya = vzyat(url);
            if (godnaya(vtoraya)) { glavnaya = vtoraya; kanal = "мобильный"; s_mobilki++; }
            else if (vtoraya.Length > glavnaya.Length) glavnaya = vtoraya;
        }
    }
    // КАПЧА — последней: она стоит денег, поэтому сперва обычный адрес, потом
    // мобильный, и лишь когда оба уткнулись в заслон, зовём решатель.
    if (!godnaya(glavnaya))
    {
        var kap = opoznat_kapchu(glavnaya);
        if (kap[0].Length > 0)
        {
            if (reshit_kapchu(kap[0], kap[1], url))
            {
                string posle = "";
                try
                {
                    var he2 = instance.ActiveTab.FindElementByTag("html", 0);
                    if (he2 != null && !he2.IsVoid) posle = he2.GetAttribute("outerhtml");
                }
                catch { }
                if (godnaya(posle)) { glavnaya = posle; kanal = "капча"; s_kapchey++; }
            }
        }
    }

    if (godnaya(glavnaya))
    {
        adresa.Add(url);
        htmly.Add(glavnaya);

        Uri baza = new Uri(url);
        string koren = baza.Scheme + "://" + baza.Host;
        var vidno = new HashSet<string>();
        var snachala = new List<string>();
        var potom = new List<string>();

        foreach (System.Text.RegularExpressions.Match m in re.Matches(glavnaya))
        {
            string ssylka = m.Groups[1].Value.Trim();
            if (ssylka.Length == 0) continue;
            string nizhniy = ssylka.ToLower();
            if (nizhniy.StartsWith("mailto:") || nizhniy.StartsWith("tel:")
                || nizhniy.StartsWith("javascript:")) continue;
            bool podhodit = false;
            foreach (string s in slova) if (nizhniy.Contains(s)) { podhodit = true; break; }
            if (!podhodit) continue;
            // технические эндпоинты движков: wp-json/oembed, feed, печатные версии.
            // Они содержат «contact» в параметрах и лезли в обход пустышками.
            if (nizhniy.Contains("wp-json") || nizhniy.Contains("oembed")
                || nizhniy.Contains("/feed") || nizhniy.Contains("?url=")
                || nizhniy.Contains("print=") || nizhniy.EndsWith(".xml")
                || nizhniy.EndsWith(".pdf") || nizhniy.EndsWith(".jpg")
                || nizhniy.EndsWith(".png")) continue;
            string polnyy;
            try { polnyy = new Uri(baza, ssylka).ToString(); } catch { continue; }
            try { if (new Uri(polnyy).Host != baza.Host) continue; } catch { continue; }
            if (polnyy == url || !vidno.Add(polnyy)) continue;
            // контактные первыми: по замеру окупаемости 13.08 страница контактов даёт
            // 853 адреса из 2157, «о компании» — 289, руководство — 25
            if (nizhniy.Contains("contact") || nizhniy.Contains("kontakt")
                || nizhniy.Contains("svyaz")) snachala.Add(polnyy);
            else potom.Add(polnyy);
        }
        snachala.AddRange(potom);

        foreach (string s in iz_karty(koren))
            if (vidno.Add(s)) snachala.Add(s);

        bool est_kontakt = false;
        foreach (string s in snachala)
        {
            string n = s.ToLower();
            if (n.Contains("contact") || n.Contains("kontakt")) { est_kontakt = true; break; }
        }
        if (!est_kontakt)
            foreach (string p in ugadki)
                if (vidno.Add(koren + p)) snachala.Add(koren + p);

        int vzyato = 0;
        var vtoroy = new List<string>();
        var nashli_pochty = pochty_so_stranicy(glavnaya);
        foreach (string k in snachala)
        {
            if (vzyato >= predel) break;
            // ПРАВИЛО ОСТАНОВКИ: две разные почты уже есть и хотя бы одна внутренняя
            // страница пройдена — дальше копать незачем. Иначе глубина в 6 страниц
            // умножилась бы на все сайты, включая те, где контакты лежат на первой же.
            if (nashli_pochty.Count >= 2 && vzyato >= 1) break;
            string h = vzyat(k);
            vzyato++;
            if (!godnaya(h)) continue;
            adresa.Add(k);
            htmly.Add(h);
            foreach (string e in pochty_so_stranicy(h)) nashli_pochty.Add(e);

            // второй уровень: у мульти-офисных сайтов карточки отделов и филиалов лежат
            // ПОД страницей контактов, и с главной на них ссылок нет
            string nk = k.ToLower();
            if (!(nk.Contains("contact") || nk.Contains("kontakt") || nk.Contains("staff")
                  || nk.Contains("rukovod"))) continue;
            foreach (System.Text.RegularExpressions.Match m in re.Matches(h))
            {
                string ss = m.Groups[1].Value.Trim();
                string ns = ss.ToLower();
                if (ns.StartsWith("mailto:") || ns.StartsWith("tel:")
                    || ns.StartsWith("javascript:")) continue;
                bool ok2 = false;
                foreach (string s in slova) if (ns.Contains(s)) { ok2 = true; break; }
                if (!ok2) continue;
                string p2;
                try { p2 = new Uri(baza, ss).ToString(); } catch { continue; }
                try { if (new Uri(p2).Host != baza.Host) continue; } catch { continue; }
                if (vidno.Add(p2)) vtoroy.Add(p2);
            }
        }

        int vzyato2 = 0;
        foreach (string k in vtoroy)
        {
            if (vzyato2 >= predel) break;
            if (nashli_pochty.Count >= 3) break;   // второй уровень нужен, пока пусто
            string h = vzyat(k);
            vzyato2++;
            if (!godnaya(h)) continue;
            adresa.Add(k);
            htmly.Add(h);
            foreach (string e in pochty_so_stranicy(h)) nashli_pochty.Add(e);
        }
    }

    // Запись. Порядок важен: сперва html, ПОТОМ .urls.txt — приёмник ориентируется на
    // список адресов, и появись он раньше страниц, разбор подхватил бы половину.
    for (int i = 0; i < htmly.Count; i++)
        System.IO.File.WriteAllText(
            System.IO.Path.Combine(papka, inn + "_" + i.ToString() + ".html"),
            htmly[i], bez_bom);
    if (htmly.Count > 0)
    {
        // канал пишем ОТДЕЛЬНЫМ файлом, а не строкой в .urls.txt: приёмник читает
        // адреса построчно, и лишняя строка сдвинула бы привязку страниц
        System.IO.File.WriteAllText(
            System.IO.Path.Combine(papka, inn + ".kanal.txt"), kanal, bez_bom);
        System.IO.File.WriteAllLines(
            System.IO.Path.Combine(papka, inn + ".urls.txt"), adresa.ToArray(),
            bez_bom);
        vsego_kompaniy++;
        vsego_stranic += htmly.Count;
    }
    else
    {
        // не далось даже с мобильного: пишем отдельно и НЕ возвращаем в очередь —
        // молчаливый повтор гонял бы мёртвый адрес по кругу
        lock (SyncObjects.ListSyncer)
            System.IO.File.AppendAllText(
                System.IO.Path.Combine(koren_obmena, "ne_otkrylis.txt"),
                inn + ";" + url + ";" + DateTime.Now.ToString("yyyy-MM-dd HH:mm") + "\r\n",
                bez_bom);
    }
    if (oshibki.Length > 0)
        System.IO.File.WriteAllText(
            System.IO.Path.Combine(papka, inn + ".err.txt"),
            oshibki.ToString(), bez_bom);

    project.SendInfoToLog(inn + ": страниц " + htmly.Count.ToString()
                          + " [" + (htmly.Count > 0 ? kanal : "не открылся") + "], "
                          + url, true);
}

project.SendInfoToLog("пачка: компаний " + vsego_kompaniy.ToString()
                      + ", страниц " + vsego_stranic.ToString()
                      + ", спасено мобильным " + s_mobilki.ToString()
                      + ", решено капч " + s_kapchey.ToString()
                      + ", спасено сменой прокси " + s_drugim_proxy.ToString()
                      + ", спасено паузой " + s_pauzoy.ToString(), true);
return vsego_stranic;
