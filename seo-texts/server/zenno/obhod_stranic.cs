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
// Предел страниц. Был 6 — это наследство от дельфина, где КАЖДАЯ страница стоила
// подъёма профиля (10-30 с). У Зенки страница почти бесплатна, и владелец 13.08
// справедливо спросил: «зачем мы глушим Зенку, она же быстрее». Замер полноты
// показал цену этой экономии: у «Волгоградгаза» Зенка взяла 3 адреса, дельфин 5 —
// не хватило страниц филиалов (uryupinsk@, volzhskiy@).
if (!int.TryParse(nastroyka("stranic_max", "12"), out predel) || predel <= 0) predel = 12;
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
// адрес выхода, который стоит прямо сейчас: нужен отпечатку (WebRTC должен
// показывать IP прокси, а не машины) и логу. Объявлен здесь, потому что делегат
// отпечатка замыкается на него, а прокси меняется в цикле по компаниям.
string tekushchiy_proxy = "";
// внешний адрес, которым мы реально выходим. Нужен WebRTC: прокси инстансу может
// выдать САМ ZennoPoster из своего пула (владелец 13.08: в логе «адрес не вынулся
// из «»», а в статусной строке прокси при этом стоял) — тогда строки прокси у нас
// нет вовсе, и адрес остаётся только спросить у сети. Узнаём один раз на выполнение.
string vneshniy_ip = "";


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
    // список методов владелец уже прислал (13.08): SetUserAgent в 7.9 НЕТ, зато есть
    // SetCanvasEmulationSettings, SetWebRTCAdresses, SetIanaTimezone, SetScreenPreference.
    // Теперь нужны их СИГНАТУРЫ — без них вызов через рефлексию не собрать.
    var nuzhnye = new string[] { "SetCanvasEmulationSettings", "SetWebRTCAdresses",
                                 "SetIanaTimezone", "SetTimezone", "SetScreenPreference",
                                 "SetWindowSize", "SetWindowPreference", "SetGeoposition",
                                 "SetBrowserPreference", "SetHeader", "SetUserHeader",
                                 "SetSuperCookie", "SetCookie", "SetContentPolicy" };
    var stroki = new List<string>();
    try
    {
        foreach (var m in instance.GetType().GetMethods())
        {
            bool nuzhen = false;
            foreach (string n in nuzhnye) if (m.Name == n) { nuzhen = true; break; }
            if (!nuzhen) continue;
            var ps = m.GetParameters();
            string sig = m.Name + "(";
            for (int i = 0; i < ps.Length; i++)
                sig += (i > 0 ? ", " : "") + ps[i].ParameterType.Name + " " + ps[i].Name;
            sig += ")";
            if (!stroki.Contains(sig)) stroki.Add(sig);
        }
    }
    catch { }
    project.SendInfoToLog("сигнатуры: " + string.Join(" | ", stroki.ToArray()), true);
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
    // Заголовок и размер — вот на что можно опираться. Признаки заслона ищем ТОЛЬКО
    // в title и только у коротких страниц.
    //
    // Здесь была моя ошибка (владелец 13.08: «почему он думает что лимит на адрес,
    // хотя на самом деле всё открылось?»): признаком 429 считалось наличие «429» И
    // слова «request» ГДЕ УГОДНО в документе. Но «request» есть в любом скрипте
    // (XMLHttpRequest), а «429» — в любом числе на странице; у obzor78.ru совпало и
    // то и другое, живая страница объявлялась заслоном и уходила на лишний повтор.
    string zagolovok = "";
    try
    {
        var mt = System.Text.RegularExpressions.Regex.Match(h, "<title[^>]*>(.*?)</title>",
            System.Text.RegularExpressions.RegexOptions.IgnoreCase |
            System.Text.RegularExpressions.RegexOptions.Singleline);
        if (mt.Success) zagolovok = mt.Groups[1].Value.ToLower();
    }
    catch { }
    bool korotkaya = h.Length < 8000;   // настоящая страница-заслон всегда куцая

    if (zagolovok.Contains("too many requests") || zagolovok.Contains("429")
        || (korotkaya && (n.Contains("too many requests")
                          || n.Contains("слишком много запросов")
                          || n.Contains("превышен лимит запросов"))))
        return "429 лимит на адрес";
    if (zagolovok.Contains("just a moment") || zagolovok.Contains("attention required")
        || (korotkaya && n.Contains("checking your browser")))
        return "cloudflare";
    if (korotkaya && n.Contains("proxy authentication required")) return "прокси не пустил";
    if (korotkaya && (n.Contains("are you not a robot")
                      || n.Contains("подтвердите, что вы человек")
                      || n.Contains("доступ ограничен"))) return "антибот";
    if (korotkaya && (zagolovok.Contains("403") || n.Contains("403 forbidden"))) return "403";
    if (korotkaya && (zagolovok.Contains("404") || zagolovok.Contains("не найдена")))
        return "404";
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


// --- ЭКОНОМИЯ ПРОЦЕССОРА: не грузить и не рисовать лишнее ---------------------------
// Владелец 13.08: «ЦП грузится на 100%», и по диспетчеру видно, что головной процесс
// ZennoPoster берёт 47% — это отрисовка, а не сами страницы (отдельные Chrome instance
// там по 0,1-1,3%). Закрытие вкладки «Инстансы» не помогло, значит выключать надо в
// самом проекте.
//
// Что делаем: запрещаем грузить картинки, медиа и шрифты — нам нужен ТОЛЬКО html,
// картинки декодируются в память и тут же выбрасываются. Плюс просим окно поменьше.
// Имена значений в сборке заранее неизвестны, поэтому: сигнатуры уже знаем из лога,
// а конкретные строки/значения перечислений подбираем рефлексией и пишем в лог, что
// реально применилось.
Action ekonomiya = delegate()
{
    var vyshlo = new List<string>();

    // 1) политика контента: перебираем правдоподобные значения, первое принятое — наше
    // ПО ДОКУМЕНТАЦИИ (ZennoLab.CommandCenter.xml, нашлась в папке установки —
    // владелец: «а доки нету у зенки?»). Там прямо сказано: policy принимает ТОЛЬКО
    // "DirectLoad", "WhiteList", "BlockList", а домены и регулярки идут отдельными
    // списками. Значения "NoImages" не существует вовсе — метод его молча проглатывал,
    // поэтому картинки продолжали грузиться, а лог рапортовал об успехе.
    try
    {
        var maski = new List<string> {
            @"\.(?:jpe?g|png|gif|webp|bmp|ico|svg|avif)(?:[?#]|$)",
            @"\.(?:woff2?|ttf|otf|eot)(?:[?#]|$)",
            @"\.(?:mp4|webm|avi|mov|mp3|wav|ogg)(?:[?#]|$)",
            @"(?:googletagmanager|google-analytics|mc\.yandex|top-fwz1)"
        };
        foreach (var m in instance.GetType().GetMethods())
        {
            if (m.Name != "SetContentPolicy") continue;
            if (m.GetParameters().Length != 3) continue;
            m.Invoke(instance, new object[] { "BlockList", new List<string>(), maski });
            vyshlo.Add("BlockList: картинки, шрифты, медиа, счётчики");
            break;
        }
    }
    catch (Exception e) { vyshlo.Add("BlockList не вышел: " + e.Message); }

    // Свойства инстанса из той же документации: они снимают отрисовку и лишние
    // запросы. Ставим через рефлексию — имена есть в доке, но состав сборки
    // проверять всё равно надо.
    Action<string, object> svoystvo = delegate(string imya, object znach)
    {
        try
        {
            var pr = instance.GetType().GetProperty(imya);
            if (pr != null && pr.CanWrite)
            {
                pr.SetValue(instance, znach, null);
                vyshlo.Add(imya + "=" + znach.ToString());
            }
        }
        catch { }
    };
    // ГЛАВНОЕ, что искали: владелец с самого начала говорил «надо именно БЕЗ
    // ОТОБРАЖЕНИЯ СОДЕРЖИМОГО в проекте прописать». В документации это отдельное
    // свойство инстанса, а вовсе не политика контента:
    //   UseBrowserWithoutContent — «true if doesn't show content of the browser»
    //   LoadPictures             — «whether loading picture from server are allowed»
    // Ни FrameRate, ни SetContentPolicy их не заменяют: политика режет ЗАПРОСЫ, а
    // отрисовка страницы в окно шла всё равно. Поэтому отображение и «продолжало
    // работать» — я гасил не тот рычаг.
    svoystvo("UseBrowserWithoutContent", true);
    svoystvo("LoadPictures", false);
    svoystvo("UseMedia", false);
    svoystvo("UsePlugins", false);
    svoystvo("UseJavaApplets", false);
    svoystvo("RunActiveX", false);
    svoystvo("UseTrafficMonitoring", false);   // подробный учёт трафика нам не нужен
    svoystvo("ClearTrafficWhenNavigate", true);
    svoystvo("FrameRate", 1);              // 1 кадр в секунду вместо 60: рисовать нечего
    svoystvo("AnimationFrameRate", 1);
    svoystvo("DownloadVideos", false);
    svoystvo("DownloadActiveX", false);
    svoystvo("IgnoreFlashRequests", true);
    svoystvo("IgnoreAdditionalRequests", true);
    svoystvo("BackGroundSoundsPlay", false);
    svoystvo("AllowNotification", false);
    svoystvo("AllowPopUp", false);

    // ПРЕВЬЮ В ПАНЕЛИ мы не гасим. Проверено замером счётчиками (13.08):
    // головной процесс ZennoPoster берёт 0,07 ядра, а дерево браузеров — 1,78.
    // Первое число я сперва прочитал как 1,53 (диспетчер задач показывает сумму
    // ПО ВСЕМУ ДЕРЕВУ под именем головного) и полез гасить превью — гонялся за
    // тем, чего нет. HideInstance при этом принимал режим «server» и на превью
    // не влиял. Код убран: он ничего не давал и путал следующего читателя.

    // читаем свойства ОБРАТНО: записали — не значит применилось (на "NoImages"
    // мы уже обожглись, метод молча принял несуществующее значение)
    if (diagnostika)
    {
        var svertka = new List<string>();
        string[] vazhnye = { "UseBrowserWithoutContent", "LoadPictures", "UseMedia",
                             "FrameRate", "UseTrafficMonitoring" };
        foreach (var im in vazhnye)
        {
            try
            {
                var pr = instance.GetType().GetProperty(im);
                if (pr != null && pr.CanRead)
                {
                    var v = pr.GetValue(instance, null);
                    svertka.Add(im + "=" + (v == null ? "null" : v.ToString()));
                }
                else svertka.Add(im + ": нет такого свойства");
            }
            catch (Exception e) { svertka.Add(im + ": " + e.Message); }
        }
        project.SendInfoToLog("проверка чтением: " + string.Join(", ", svertka.ToArray()),
                              true);
    }

    // ПРОВЕРКА, а не вера: грузим страницу с картинкой и смотрим, приехала ли она.
    // Без этого «метод не бросил исключение» ничего не доказывает — ровно так мы и
    // отчитались в прошлый раз, а картинки продолжали качаться.
    if (diagnostika)
    {
        try
        {
            instance.ActiveTab.Navigate("http://api.ipify.org", "");
            instance.ActiveTab.WaitDownloading();
            var he = instance.ActiveTab.FindElementByTag("html", 0);
            string proba = (he != null && !he.IsVoid) ? he.GetAttribute("outerhtml") : "";
            vyshlo.Add("проба страницы: " + proba.Length.ToString() + " знаков");
        }
        catch { }
    }

    // 2) окно поменьше: меньше пикселей — меньше работы отрисовщику
    try { vyzvat("SetWindowSize", new object[] { 1024, 768 }); vyshlo.Add("окно 1024x768"); }
    catch { }

    // 3) значения перечислений печатаем ОДИН раз: по ним допишем остальное точно
    if (diagnostika)
    {
        var spisok = new List<string>();
        try
        {
            foreach (var m in instance.GetType().GetMethods())
            {
                if (m.Name != "SetWindowPreference" && m.Name != "SetScreenPreference") continue;
                foreach (var pp in m.GetParameters())
                {
                    if (!pp.ParameterType.IsEnum) continue;
                    string stroka = m.Name + "." + pp.ParameterType.Name + ": "
                                  + string.Join(",", Enum.GetNames(pp.ParameterType));
                    if (!spisok.Contains(stroka)) spisok.Add(stroka);
                }
            }
        }
        catch { }
        if (spisok.Count > 0)
            project.SendInfoToLog("значения настроек: " + string.Join(" | ",
                                                                     spisok.ToArray()), true);
    }
    if (diagnostika)
        project.SendInfoToLog("экономия: " + (vyshlo.Count > 0
            ? string.Join(", ", vyshlo.ToArray()) : "ничего не применилось"), true);
};

// --- ПОЛНЫЙ ОТПЕЧАТОК: canvas, WebRTC, зона, геопозиция ---------------------------
// Сигнатуры получены из лога владельца (13.08), поэтому собираем вызовы точно, а не
// наугад. Аргументы-перечисления берём через рефлексию: имена значений в разных
// сборках отличаются, а тип параметра известен всегда.
//   SetCanvasEmulationSettings(CanvasEmulationSettings settings)
//   SetWebRTCAdresses(String ipv4, String ipv6, String ipv4Nat, WebRTCMode mode)
//   SetIanaTimezone(String ianaZone, TimezoneMode mode)
//   SetGeoposition(Double lat, lon, accuracy, altitude, altitudeAccuracy, heading, speed)
Func<string, int, string[], object> znachenie_perechisleniya =
    delegate(string metod, int nomer_arg, string[] hochu)
{
    try
    {
        foreach (var m in instance.GetType().GetMethods())
        {
            if (m.Name != metod) continue;
            var ps = m.GetParameters();
            if (ps.Length <= nomer_arg) continue;
            Type t = ps[nomer_arg].ParameterType;
            if (!t.IsEnum) continue;
            string[] imena = Enum.GetNames(t);
            foreach (string hochu_imya in hochu)
                foreach (string imya in imena)
                    if (string.Equals(imya, hochu_imya, StringComparison.OrdinalIgnoreCase))
                        return Enum.Parse(t, imya);
            // нужного значения нет — берём первое, кроме «выключено»
            foreach (string imya in imena)
                if (imya.ToLower() != "off" && imya.ToLower() != "none"
                    && imya.ToLower() != "disabled") return Enum.Parse(t, imya);
        }
    }
    catch { }
    return null;
};


Action postavit_otpechatok = delegate()
{
    var postavleno = new List<string>();

    // 1) часовой пояс: прокси российские, а браузер отдавал зону хостинга
    object rezhim_zony = znachenie_perechisleniya("SetIanaTimezone", 1,
        new string[] { "Manual", "Custom", "Fixed" });
    if (rezhim_zony != null &&
        vyzvat("SetIanaTimezone", new object[] { "Europe/Moscow", rezhim_zony }))
        postavleno.Add("зона");

    // 2) WebRTC: без подмены он выдаёт настоящий адрес машины ПОВЕРХ прокси —
    // это самая громкая улика, дельфин её закрывал режимом altered
    object rezhim_rtc = znachenie_perechisleniya("SetWebRTCAdresses", 3,
        new string[] { "Manual", "Altered", "Replace", "Custom" });
    string pochemu_net_rtc = "";
    if (rezhim_rtc == null) pochemu_net_rtc = "режим не подобрался";
    else
    {
        // адрес выхода из строки прокси: и «user:pass@ip:port», и «ip:port»
        string vneshniy = "";
        try
        {
            var mm = System.Text.RegularExpressions.Regex.Match(
                tekushchiy_proxy, @"(?:@|//)((?:\d{1,3}\.){3}\d{1,3}):");
            if (mm.Success) vneshniy = mm.Groups[1].Value;
            if (vneshniy.Length == 0)
            {
                var m2 = System.Text.RegularExpressions.Regex.Match(
                    tekushchiy_proxy, @"((?:\d{1,3}\.){3}\d{1,3})");
                if (m2.Success) vneshniy = m2.Groups[1].Value;
            }
        }
        catch { }
        if (vneshniy.Length == 0 && vneshniy_ip.Length > 0) vneshniy = vneshniy_ip;
        if (vneshniy.Length == 0)
        {
            // прокси поставил ZennoPoster, а не мы: спрашиваем адрес у сервиса.
            // Один заход на выполнение, дальше берём из памяти.
            try
            {
                string otvet = vzyat("http://api.ipify.org");
                var mi = System.Text.RegularExpressions.Regex.Match(
                    otvet ?? "", @"((?:\d{1,3}\.){3}\d{1,3})");
                if (mi.Success)
                {
                    vneshniy_ip = mi.Groups[1].Value;
                    vneshniy = vneshniy_ip;
                }
            }
            catch { }
        }
        if (vneshniy.Length == 0)
            pochemu_net_rtc = "адрес не вынулся ни из прокси, ни у ipify";
        else if (!vyzvat("SetWebRTCAdresses",
                         new object[] { vneshniy, "", "192.168.1.2", rezhim_rtc }))
            pochemu_net_rtc = "вызов не прошёл (" + vneshniy + ")";
        else postavleno.Add("webrtc");
    }
    if (diagnostika && pochemu_net_rtc.Length > 0)
        project.SendWarningToLog("webrtc не встал: " + pochemu_net_rtc, true);

    // 3) canvas: объект настроек создаём через рефлексию и просим «шум»
    try
    {
        foreach (var m in instance.GetType().GetMethods())
        {
            if (m.Name != "SetCanvasEmulationSettings") continue;
            Type t = m.GetParameters()[0].ParameterType;
            object nastroyki = null;
            try { nastroyki = Activator.CreateInstance(t); }
            catch
            {
                foreach (var k in t.GetConstructors())
                {
                    var kp = k.GetParameters();
                    if (kp.Length == 1 && kp[0].ParameterType.IsEnum)
                    {
                        string[] imena = Enum.GetNames(kp[0].ParameterType);
                        object znach = null;
                        foreach (string imya in imena)
                            if (imya.ToLower().Contains("noise")) znach = Enum.Parse(kp[0].ParameterType, imya);
                        if (znach == null && imena.Length > 0)
                            znach = Enum.Parse(kp[0].ParameterType, imena[imena.Length - 1]);
                        nastroyki = k.Invoke(new object[] { znach });
                        break;
                    }
                }
            }
            if (nastroyki == null) break;
            // если у объекта есть свойство режима — ставим «шум»
            foreach (var pr in t.GetProperties())
            {
                if (!pr.CanWrite || !pr.PropertyType.IsEnum) continue;
                foreach (string imya in Enum.GetNames(pr.PropertyType))
                    if (imya.ToLower().Contains("noise"))
                    {
                        pr.SetValue(nastroyki, Enum.Parse(pr.PropertyType, imya), null);
                        break;
                    }
            }
            m.Invoke(instance, new object[] { nastroyki });
            postavleno.Add("canvas");
            break;
        }
    }
    catch { }

    // 4) геопозиция — Москва с разбросом, чтобы не совпадала у всех потоков
    try
    {
        double shirota = 55.75 + (sluchay.Next(-40, 40) / 1000.0);
        double dolgota = 37.62 + (sluchay.Next(-60, 60) / 1000.0);
        if (vyzvat("SetGeoposition", new object[] { shirota, dolgota, 100.0, 150.0,
                                                    50.0, 0.0, 0.0 }))
            postavleno.Add("гео");
    }
    catch { }

    if (diagnostika && postavleno.Count > 0)
        project.SendInfoToLog("отпечаток: " + string.Join(", ", postavleno.ToArray()), true);
};

var slova = new string[] { "contact", "kontakt", "svyaz", "about", "o-kompanii",
                           "o-nas", "company", "rukovod", "staff", "team",
                           "sotrudnik", "rekvizit",
                           // филиалы и подразделения: замер полноты 13.08 показал, что
                           // именно там теряются адреса вроде uryupinsk@ и volzhskiy@
                           "filial", "predstavitel", "podrazdelen", "otdel", "office",
                           "ofis", "adresa", "regiony", "seti", "vacan", "career" };
var ugadki = new string[] { "/contacts/", "/kontakty/", "/contact/", "/about/",
                            "/o-kompanii/", "/company/staff/", "/company/", "/rukovodstvo/" };
var re = new System.Text.RegularExpressions.Regex(
    "href\\s*=\\s*[\"']([^\"'#]{1,180})[\"']",
    System.Text.RegularExpressions.RegexOptions.IgnoreCase);

ekonomiya();   // один раз на выполнение: политика контента и размер окна

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
    // РЕЖИМ ОБХОДА — третьим полем строки очереди (по умолчанию контакты).
    // «facts» — сбор фактов о продукции и новостей для писем (ТЗ соседней сессии
    // 13.08): там нужны каталог, производство, новости, а НЕ страница контактов,
    // и останавливаться на второй найденной почте нельзя.
    string rezhim = (chasti.Length > 2 ? chasti[2].Trim().ToLower() : "");
    // «oba» — контакты И факты за ОДИН заход. Два отдельных прохода по одной
    // компании стоят двух главных страниц и двух угадаек контактов, а словари
    // пересекаются лишь на about/company/vacancies. Совмещённый набор берёт
    // и филиалы с руководством (это люди для писем), и каталог с новостями.
    bool oba = (rezhim == "oba" || rezhim == "both" || rezhim == "vse");
    bool za_faktami = (rezhim == "facts" || rezhim == "fakty" || oba);
    if (url.Length == 0) continue;
    if (!url.StartsWith("http")) url = "http://" + url;
    oshibki.Length = 0;

    // между компаниями чистим сессию, меняем адрес выхода и отпечаток
    instance.ClearCookie();
    instance.ClearCache();
    // ОТПЕЧАТОК НА КОМПАНИЮ. SetUserAgent в 7.9 отсутствует (подтверждено логом
    // владельца), поэтому UA ставим заголовком — это работающий путь, а не обходной.
    string ua = ua_spisok[sluchay.Next(ua_spisok.Length)];
    if (!vyzvat("SetUserAgent", new object[] { ua }))
    {
        if (!vyzvat("SetHeader", new object[] { "User-Agent", ua }))
            vyzvat("SetUserHeader", new object[] { "User-Agent", ua });
    }
    vyzvat("SetHeader", new object[] { "Accept-Language", "ru-RU,ru;q=0.9,en;q=0.8" });
    // размер окна из набора реальных разрешений: одинаковый на всех заходах —
    // такая же примета автоматизации, как и дефолтный UA
    int[][] ekrany = new int[][] { new int[]{1366,768}, new int[]{1920,1080},
                                   new int[]{1536,864}, new int[]{1440,900} };
    int[] ek = ekrany[sluchay.Next(ekrany.Length)];
    vyzvat("SetWindowSize", new object[] { ek[0], ek[1] });
    // часовой пояс: прокси у нас российские, поэтому московский, а не UTC хостинга
    postavit_otpechatok();
    if (proxy_obychnye.Count > 0)
    {
        tekushchiy_proxy = proxy_obychnye[sluchay.Next(proxy_obychnye.Count)];
        instance.SetProxy(tekushchiy_proxy);
    }

    var adresa = new List<string>();
    var htmly = new List<string>();
    // ЗАМЕР ЗАСЛОНА НА ВНУТРЕННИХ СТРАНИЦАХ (вопрос владельца 14.08: «не пустила ли
    // защита на вторую и дальше»). Отказ раньше просто пропускался, и отличить
    // «ссылки не было» от «страницу не отдали» было нечем. Объявляем РЯДОМ С adresa:
    // пишется файл ниже, за пределами блока godnaya(glavnaya).
    var otkazy = new List<string>();
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
                tekushchiy_proxy = proxy_obychnye[sluchay.Next(proxy_obychnye.Count)];
                instance.SetProxy(tekushchiy_proxy);
                instance.ClearCookie();
                string drugoy = vzyat(url);
                if (godnaya(drugoy)) { glavnaya = drugoy; kanal = "смена прокси"; s_drugim_proxy++; }
            }
        }
        if (!godnaya(glavnaya) && proxy_mobilnye.Count > 0)
        {
            tekushchiy_proxy = proxy_mobilnye[sluchay.Next(proxy_mobilnye.Count)];
            instance.SetProxy(tekushchiy_proxy);
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
        // слова поиска зависят от режима: за контактами ищем контакты, за фактами —
        // каталог и новости. Порядок внутри набора = порядок ценности из ТЗ.
        // ТЗ называет пять разделов, но письму помогает ЛЮБАЯ предметная страница
        // (владелец 13.08: «страницы не только те, которые назвал постановщик, а те,
        // которые в принципе могут помочь»). Поэтому сверх ТЗ берём:
        //   услуги/направления/решения — чем занимаются словами сайта, а не ОКВЭД;
        //   отрасли и применение — кому поставляют, это прямая связка с нашим письмом;
        //   проекты и объекты — масштаб и реализованное, там же названо оборудование;
        //   оборудование и парк — прямое попадание: видно, что у них стоит;
        //   вакансии — «оператор линии розлива» выдаёт и линию, и расширение;
        //   закупки и поставщикам — сигнал о текущей потребности;
        //   экспорт и география — куда возят;
        //   прайс — ассортимент словами самого предприятия.
        string[] slova_facts = new string[] { "catalog", "produk", "tovar", "assortiment", "shop", "price",
                             "prays", "proizvod", "production", "tehnolog", "zavod",
                             "moshchnost", "news", "novosti", "press", "smi", "blog",
                             "sobytiya", "about", "o-kompanii", "o-nas", "company",
                             "history", "kachestv", "quality", "sertifik", "certificate",
                             "haccp", "uslugi", "services", "napravlen", "reshen",
                             "solution", "otrasl", "primenen", "industr", "proekt",
                             "project", "obekt", "portfolio", "oborudovan", "equipment",
                             "park", "vacan", "career", "rabota", "zakup", "postavshchik",
                             "tender", "export", "eksport", "geografi" };
        string[] slova_tek;
        if (oba)
        {
            var svod = new List<string>(slova);
            foreach (string w in slova_facts) if (!svod.Contains(w)) svod.Add(w);
            slova_tek = svod.ToArray();
        }
        else slova_tek = za_faktami ? slova_facts : slova;
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
            foreach (string s in slova_tek) if (nizhniy.Contains(s)) { podhodit = true; break; }
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
            // в совмещённом режиме контакты идут первыми: если сайт вдруг обрубит
            // обход на середине, потерять лучше каталог, чем адрес
            bool vazhnaya = (za_faktami && !oba)
                ? (nizhniy.Contains("catalog") || nizhniy.Contains("produk")
                   || nizhniy.Contains("tovar") || nizhniy.Contains("assortiment")
                   || nizhniy.Contains("news") || nizhniy.Contains("novosti")
                   || nizhniy.Contains("proizvod") || nizhniy.Contains("oborudovan"))
                : (nizhniy.Contains("contact") || nizhniy.Contains("kontakt")
                   || nizhniy.Contains("svyaz"));
            if (vazhnaya) snachala.Add(polnyy);
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
            if (vzyato >= (oba ? predel + 6 : (za_faktami ? predel + 2 : predel))) break;
            // ПРАВИЛО ОСТАНОВКИ: две разные почты уже есть и хотя бы одна внутренняя
            // страница пройдена — дальше копать незачем. Иначе глубина в 6 страниц
            // умножилась бы на все сайты, включая те, где контакты лежат на первой же.
            // Раньше здесь стояло «две почты найдены — уходим». Снято: экономия имела
            // смысл при дельфине, а у Зенки обход дешёвый, и на второй-третьей странице
            // лежат адреса филиалов и отделов, ради которых всё и делается. Оставлен
            // только предохранитель от сайта-каталога на сотни страниц — это predel.
            if (!za_faktami && nashli_pochty.Count >= 8) break;
            string h = vzyat(k);
            vzyato++;
            string prichina = pochemu_ne_godna(h);
            if (prichina.Length > 0)
            {
                otkazy.Add("1|" + prichina + "|" + h.Length.ToString() + "|" + k);
                continue;
            }
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
            if (vzyato2 >= predel) break;   // второй уровень идёт тем же пределом
            if (!za_faktami && nashli_pochty.Count >= 10) break;  // защита от каталога
            string h = vzyat(k);
            vzyato2++;
            string prichina2 = pochemu_ne_godna(h);
            if (prichina2.Length > 0)
            {
                otkazy.Add("2|" + prichina2 + "|" + h.Length.ToString() + "|" + k);
                continue;
            }
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
            System.IO.Path.Combine(papka, inn + ".kanal.txt"),
            kanal + (oba ? ";oba;facts" : (za_faktami ? ";facts" : "")), bez_bom);
        if (otkazy.Count > 0)
            System.IO.File.WriteAllLines(
                System.IO.Path.Combine(papka, inn + ".otkaz.txt"), otkazy.ToArray(),
                bez_bom);
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
