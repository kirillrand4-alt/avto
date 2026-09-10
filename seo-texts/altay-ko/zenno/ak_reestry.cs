// ak_reestry.cs — кубик ZennoPoster для закрытых площадок и реестров (Алтайский край × компрессорное оборудование).
// Ставится ОДНИМ блоком «Свой код» (Own code) в новом проекте. Многопоточный: каждый поток берёт своё задание
// из ak_zadaniya.txt и отмечает его в ak_otdano.txt, поэтому задания не дублируются.
//
// Папка обмена (переменная проекта obmen, по умолчанию C:\seostat\drop\zenno):
//   ak_zadaniya.txt   вход:  <id>;<источник>;<url>;<текст_которого_ждать>
//   ak_otdano.txt     кто уже взят в работу (id)
//   ak_gotovo\        выход: <id>.html, <id>_p2.html, <id>_p3.html ...
//   ak_vypolneno.txt  <id> \t <источник> \t <страниц> \t ok
//   ak_otkazy.txt     <id> \t <источник> \t причина
//   proxy.txt         прокси, по строке (любой формат, понятный instance.SetProxy)
//
// Настройки проекта (переменные, все необязательные):
//   obmen        путь к папке обмена
//   stranic      сколько страниц пагинации проходить максимум (по умолчанию 40)
//   zhdat_sek    сколько секунд ждать текст на странице (по умолчанию 60)
//   kapcha       1 = решать капчу через настроенный в ZennoPoster сервис (по умолчанию 1)

string obmen = project.Variables["obmen"].Value;
if (string.IsNullOrEmpty(obmen)) obmen = @"C:\seostat\drop\zenno";
int maxStranic = 40; int.TryParse(project.Variables["stranic"].Value, out maxStranic);
if (maxStranic <= 0) maxStranic = 40;
int zhdat = 60; int.TryParse(project.Variables["zhdat_sek"].Value, out zhdat);
if (zhdat <= 0) zhdat = 60;
bool reshatKapchu = project.Variables["kapcha"].Value != "0";

string fZad = System.IO.Path.Combine(obmen, "ak_zadaniya.txt");
string fOtdano = System.IO.Path.Combine(obmen, "ak_otdano.txt");
string dGotovo = System.IO.Path.Combine(obmen, "ak_gotovo");
string fVyp = System.IO.Path.Combine(obmen, "ak_vypolneno.txt");
string fOtk = System.IO.Path.Combine(obmen, "ak_otkazy.txt");
System.IO.Directory.CreateDirectory(dGotovo);

// ---------- 1. взять задание (под глобальной блокировкой, чтобы потоки не подрались)
string zadanie = null;
lock (SyncObjects.InputSyncer)
{
    var vzyaty = new System.Collections.Generic.HashSet<string>();
    if (System.IO.File.Exists(fOtdano))
        foreach (var l in System.IO.File.ReadAllLines(fOtdano))
            if (l.Trim().Length > 0) vzyaty.Add(l.Trim());

    if (!System.IO.File.Exists(fZad)) { project.SendInfoToLog("нет файла заданий " + fZad); return "net_zadaniy"; }
    foreach (var l in System.IO.File.ReadAllLines(fZad, System.Text.Encoding.UTF8))
    {
        var s = l.Trim();
        if (s.Length == 0) continue;
        var id = s.Split(';')[0].Trim();
        if (vzyaty.Contains(id)) continue;
        zadanie = s;
        System.IO.File.AppendAllText(fOtdano, id + "\r\n", System.Text.Encoding.UTF8);
        break;
    }
}
if (zadanie == null) { project.SendInfoToLog("задания кончились"); return "net_zadaniy"; }

var ch = zadanie.Split(';');
string id = ch[0].Trim();
string istochnik = ch.Length > 1 ? ch[1].Trim() : "";
string url = ch.Length > 2 ? ch[2].Trim() : "";
string zhdatTekst = ch.Length > 3 ? ch[3].Trim() : "";
project.SendInfoToLog("задание " + id + " (" + istochnik + ") " + url);

// ---------- 2. прокси
try
{
    string fProxy = System.IO.Path.Combine(obmen, "proxy.txt");
    if (System.IO.File.Exists(fProxy))
    {
        var pr = System.IO.File.ReadAllLines(fProxy);
        var zhivye = new System.Collections.Generic.List<string>();
        foreach (var p in pr) if (p.Trim().Length > 5) zhivye.Add(p.Trim());
        if (zhivye.Count > 0) instance.SetProxy(zhivye[new Random(Guid.NewGuid().GetHashCode()).Next(zhivye.Count)]);
    }
}
catch (Exception e) { project.SendWarningToLog("прокси не поставился: " + e.Message); }

// ---------- 3. вспомогательное: капча и ожидание текста
Func<bool> reshitKapchu = () =>
{
    if (!reshatKapchu) return false;
    try
    {
        var t = instance.ActiveTab;
        // reCAPTCHA v2
        var frame = t.FindElementByAttribute("iframe", "src", "recaptcha", "text", 0);
        if (!frame.IsVoid)
        {
            string sitekey = t.FindElementByAttribute("div", "class", "g-recaptcha", "text", 0).GetAttribute("data-sitekey");
            if (!string.IsNullOrEmpty(sitekey))
            {
                string otvet = ZennoPoster.CaptchaRecognition("RecaptchaV2.dll", sitekey + "|" + t.URL, "");
                if (!string.IsNullOrEmpty(otvet))
                {
                    t.MainDocument.EvaluateScript("document.getElementById('g-recaptcha-response').innerHTML='" + otvet + "';");
                    var knopka = t.FindElementByAttribute("button", "type", "submit", "text", 0);
                    if (!knopka.IsVoid) knopka.Click(); else t.MainDocument.EvaluateScript("document.forms[0] && document.forms[0].submit();");
                    t.WaitDownloading();
                    return true;
                }
            }
        }
        // картиночная капча
        var img = t.FindElementByAttribute("img", "src", "captcha", "text", 0);
        if (!img.IsVoid)
        {
            string otvet = ZennoPoster.CaptchaRecognition("", img.DrawToBitmap(false), "");
            var pole = t.FindElementByAttribute("input", "name", "captcha", "text", 0);
            if (!pole.IsVoid && !string.IsNullOrEmpty(otvet))
            {
                pole.SetValue(otvet, "Full", false);
                var kn = t.FindElementByAttribute("button", "type", "submit", "text", 0);
                if (!kn.IsVoid) kn.Click();
                t.WaitDownloading();
                return true;
            }
        }
    }
    catch (Exception e) { project.SendWarningToLog("капча: " + e.Message); }
    return false;
};

Func<string, bool> zhdatPoyavleniya = (tekst) =>
{
    var kray = DateTime.Now.AddSeconds(zhdat);
    while (DateTime.Now < kray)
    {
        instance.ActiveTab.WaitDownloading();
        string h = instance.ActiveTab.DocumentText ?? "";
        if (string.IsNullOrEmpty(tekst) && h.Length > 5000) return true;
        if (!string.IsNullOrEmpty(tekst) && h.IndexOf(tekst, StringComparison.OrdinalIgnoreCase) >= 0) return true;
        if (h.IndexOf("captcha", StringComparison.OrdinalIgnoreCase) >= 0 || h.IndexOf("робот", StringComparison.OrdinalIgnoreCase) >= 0)
            if (reshitKapchu()) continue;
        System.Threading.Thread.Sleep(2000);
    }
    return false;
};

// ---------- 4. открыть и сохранить, пройти пагинацию
int stranic = 0;
string prichina = "";
try
{
    instance.ActiveTab.Navigate(url, "");
    instance.ActiveTab.WaitDownloading();
    if (!zhdatPoyavleniya(zhdatTekst))
    {
        prichina = "не дождались текста: " + zhdatTekst;
    }
    else
    {
        for (int p = 1; p <= maxStranic; p++)
        {
            string html = instance.ActiveTab.DocumentText ?? "";
            if (html.Length < 500) { prichina = "пустая страница на " + p; break; }
            string imya = p == 1 ? id + ".html" : id + "_p" + p + ".html";
            System.IO.File.WriteAllText(System.IO.Path.Combine(dGotovo, imya), html, System.Text.Encoding.UTF8);
            stranic = p;

            // следующая страница: типовые варианты у всех перечисленных площадок
            var t = instance.ActiveTab;
            var dalee = t.FindElementByAttribute("a", "class", "pagination__next", "text", 0);
            if (dalee.IsVoid) dalee = t.FindElementByAttribute("a", "rel", "next", "text", 0);
            if (dalee.IsVoid) dalee = t.FindElementByAttribute("a", "innertext", "Следующая", "text", 0);
            if (dalee.IsVoid) dalee = t.FindElementByAttribute("a", "innertext", "Далее", "text", 0);
            if (dalee.IsVoid) dalee = t.FindElementByAttribute("a", "innertext", (p + 1).ToString(), "text", 0);
            if (dalee.IsVoid) break;
            dalee.Click();
            t.WaitDownloading();
            System.Threading.Thread.Sleep(1500);
            if (!zhdatPoyavleniya(zhdatTekst)) break;
        }
    }
}
catch (Exception e) { prichina = e.Message; }

// ---------- 5. отчитаться
lock (SyncObjects.OutputSyncer)
{
    if (stranic > 0)
        System.IO.File.AppendAllText(fVyp, id + "\t" + istochnik + "\t" + stranic + "\tok\r\n", System.Text.Encoding.UTF8);
    else
        System.IO.File.AppendAllText(fOtk, id + "\t" + istochnik + "\t" + (prichina.Length > 0 ? prichina : "без страниц") + "\r\n", System.Text.Encoding.UTF8);
}
project.SendInfoToLog("готово " + id + ": страниц " + stranic + (prichina.Length > 0 ? (" | " + prichina) : ""));
return stranic > 0 ? "ok" : "otkaz";
