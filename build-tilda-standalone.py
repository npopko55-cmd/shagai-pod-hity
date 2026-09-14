#!/usr/bin/env python3
"""
«Шагай под хиты» -> блоки T123 «HTML-код» для Тильды. Стили и скрипт едут
ВНУТРИ блоков, внешнего хостинга для них нет.

Контракт взят из antiotek/build-tilda-standalone.py (проверен на проде), все
его решения сохранены — причины описаны у кода. Отличия этого проекта
отмечены пометкой «ЗДЕСЬ».

Запуск:
  python3 build-tilda-standalone.py              обычная сборка
  python3 build-tilda-standalone.py --no-compat  без поправок под Тильду
                                                 (только для проверки паритета)
Пишет:
  tilda-standalone/            сырые блоки: style-N, markup-N-<секция>, script
  ДЛЯ ТИЛЬДЫ/                  те же блоки с номерами порядка вставки + ПРОЧТИ ПЕРВЫМ.txt
  _design/tilda-preview.html   страница из блоков в обёртках, как у Тильды
  tilda-assets.json            карта assets/... -> URL на Тильде (создаётся пустой)

Исходники (index.html, styles.css, script.js) только читаются — сборщик
перезапускается на свежих файлах без ручных правок.
"""
import base64
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
LIMIT = 30000                          # лимит Тильды на один блок
MARKUP_LIMIT = LIMIT - 2000            # разметка: запас, впритык Тильду не подводим
CSS_CHUNK = (LIMIT - 3000) * 3 // 4    # байт CSS: base64 +1/3, плюс ~400 знаков обвязки
CDN = "https://npopko55-cmd.github.io/shagai-pod-hity"
SCOPE = ".hits"
COMPAT = "--no-compat" not in sys.argv[1:]

OUT = BASE / "tilda-standalone"
HAND = BASE / "ДЛЯ ТИЛЬДЫ"
PREVIEW = BASE / "_design" / "tilda-preview.html"

# Порядок и подписи секций. Новая <section id="..."> тоже станет своим блоком.
SECTIONS = [
    ("top", "первый экран"),
    ("problem", "почему бросают"),
    ("compare", "сравнение"),
    ("format", "формат"),
    ("tariffs", "тарифы"),
    ("stories", "истории участниц"),
    ("trainers", "тренеры"),
]
SLOT_ATTRS = [
    ("data-video", "ролики, секция «Формат»"),
    ("data-audio", "музыка, первый экран"),
    ("data-photo", "фото тренеров"),
]

html = (BASE / "index.html").read_text(encoding="utf-8")
css = (BASE / "styles.css").read_text(encoding="utf-8")
js = (BASE / "script.js").read_text(encoding="utf-8")
warnings = []

m = re.search(r'<link[^>]+fonts\.googleapis\.com/css2[^>]*>', html)
if not m:
    raise SystemExit("Не нашёл <link> шрифтов Google в index.html")
FONT_LINK = m.group(0)


# =========================================================================
# 1. CSS
# =========================================================================
def skip_string(text, i):
    """text[i] — кавычка; вернуть индекс сразу за закрывающей."""
    q, j, n = text[i], i + 1, len(text)
    while j < n:
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == q:
            return j + 1
        j += 1
    return n


def strip_comments(text):
    # Комментарии убираем ДО разбора: внутри них попадаются скобки и точки с
    # запятой, парсер antiotek принимал их за границы правил и терял :root.
    # ЗДЕСЬ в комментариях ещё и «<br>», «< 900» — угловые скобки в готовый CSS
    # попадать не должны.
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            j = skip_string(text, i)
            out.append(text[i:j])
            i = j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def minify(text):
    """ЗДЕСЬ минификатор antiotek ломал бы вёрстку: он снимал пробелы вокруг «:»,
    и `.hits :where(h1, …)` (сброс у потомков) превращался в `.hits:where(h1, …)`
    (правило на саму обёртку) — у заголовков вернулись бы поля браузера. Поэтому
    пробелы схлопываем до одного и убираем только рядом с { } ; , — строки
    в кавычках не трогаем вовсе."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            j = skip_string(text, i)
            out.append(text[i:j])
            i = j
            continue
        if c.isspace():
            j = i
            while j < n and text[j].isspace():
                j += 1
            prev = out[-1][-1:] if out else ""
            nxt = text[j] if j < n else ""
            if prev and nxt and prev not in "{};," and nxt not in "{};,":
                out.append(" ")
            i = j
            continue
        if c == "}" and out and out[-1] == ";":
            out.pop()
        out.append(c)
        i += 1
    return "".join(out)


def parse_blocks(text):
    """Верхнеуровневые куски CSS со счётом скобок, а не регулярками: на
    @media регулярка в antiotek теряла закрывающие скобки. Возвращает
    ('rule' | 'at', заголовок, содержимое) и ('raw', текст, '')."""
    out, i, n = [], 0, len(text)
    while i < n:
        j, brace = i, -1
        while j < n:
            if text[j] in "\"'":
                j = skip_string(text, j)
                continue
            if text[j] == "{":
                brace = j
                break
            j += 1
        if brace < 0:
            tail = text[i:].strip()
            if tail.strip(";").strip():
                out.append(("raw", tail, ""))
            break
        prelude = text[i:brace]
        sep = prelude.rfind(";")          # @import …; перед правилом
        if sep >= 0:
            if prelude[:sep].strip(";").strip():
                out.append(("raw", prelude[:sep + 1].strip(), ""))
            prelude = prelude[sep + 1:]
        head = prelude.strip()
        depth, k = 1, brace + 1
        while k < n and depth:
            if text[k] in "\"'":
                k = skip_string(text, k)
                continue
            if text[k] == "{":
                depth += 1
            elif text[k] == "}":
                depth -= 1
            k += 1
        if depth:
            raise SystemExit(f"CSS: не закрыта скобка у «{head[:60]}»")
        out.append(("at" if head.startswith("@") else "rule", head, text[brace + 1:k - 1]))
        i = k
    return out


def split_top(s, sep):
    """Делим по sep только на верхнем уровне. ЗДЕСЬ `split(",")` из antiotek
    рвал бы `:where(img, video)` пополам и префиксовал обрывки."""
    parts, cur, depth, i, n = [], [], 0, 0, len(s)
    while i < n:
        c = s[i]
        if c in "\"'":
            j = skip_string(s, i)
            cur.append(s[i:j])
            i = j
            continue
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif c == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    parts.append("".join(cur))
    return parts


# ---------------------------------------------------------------------------
# ИЗОЛЯЦИЯ ОТ ОСТАЛЬНОЙ СТРАНИЦЫ (как в antiotek)
# Префикс получают ВСЕ правила, а не только голые теги: если ограничить только
# теги, у `.scope h2` станет выше вес, чем у класса, и тег перебьёт класс.
# ЗДЕСЬ вся вёрстка уже живёт внутри .hits, поэтому правила, которые начинаются
# с самого класса .hits, не трогаем. Проверка — именно на класс: `.hits-hero`
# тоже «начинается с .hits», и startswith из antiotek оставил бы его без префикса.
# ---------------------------------------------------------------------------
OWN_SCOPE = re.compile(r"^\.hits(?![\w-])")
NESTED_AT = re.compile(r"@(media|supports|container|layer|document|scope)\b", re.I)
PSEUDO_EL = re.compile(r"(::?(?:before|after|first-line|first-letter|marker|placeholder"
                       r"|selection|backdrop|-webkit-[\w-]+))$")
child_rewrites = []


def scope_one(sel):
    s = sel.strip()
    if not s or s.startswith(":root") or OWN_SCOPE.match(s):
        return s
    m = re.match(r"^(html|body)(?![\w-])", s)
    if m:
        rest = s[m.end():].strip()
        return f"{SCOPE} {rest}" if rest else SCOPE
    return f"{SCOPE} {s}"


def compound_bounds(s, from_end):
    depth = 0
    rng = range(len(s) - 1, -1, -1) if from_end else range(len(s))
    for k in rng:
        c = s[k]
        if c in (")]" if from_end else "(["):
            depth += 1
        elif c in ("([" if from_end else ")]"):
            depth -= 1
        elif depth == 0 and (c.isspace() or c in "+~"):
            return k + 1 if from_end else k
    return 0 if from_end else len(s)


def no_child_combinator(sel):
    """ЗДЕСЬ в стилях есть дочерний комбинатор `>` (три правила). В готовом CSS
    угловых скобок быть не должно, поэтому `A > B` пишем как
    `A B:not(:where(A * B))`: «B внутри A, но не глубже прямого потомка».
    Вес тот же — у :not(:where(…)) он нулевой. Верно, пока A не вложен в A
    (у .hits-section, .hits-compare__note, .hits-trainer__photo так и есть)."""
    parts = split_top(sel, ">")
    if len(parts) == 1:
        return sel
    res = parts[0].rstrip()
    for right in parts[1:]:
        right = right.strip()
        left = res[compound_bounds(res, True):]
        cut = compound_bounds(right, False)
        first, rest = right[:cut], right[cut:]
        pm = PSEUDO_EL.search(first)
        base, pseudo = (first[:pm.start()], pm.group(1)) if pm else (first, "")
        res = f"{res} {base}:not(:where({left} * {base})){pseudo}{rest}"
    child_rewrites.append(sel)
    return res


def scope_css(text):
    out = []
    for kind, head, inner in parse_blocks(text):
        if kind == "raw":
            out.append(head)
        elif kind == "at":
            # ЗДЕСЬ @supports лежит внутри @media — рекурсия заходит на любую глубину.
            # У @keyframes внутри проценты, у @font-face селекторов нет — не трогаем.
            if NESTED_AT.match(head):
                out.append(head + "{" + scope_css(inner) + "}")
            else:
                out.append(head + "{" + inner + "}")
        else:
            sels = [no_child_combinator(scope_one(p)) for p in split_top(head, ",") if p.strip()]
            out.append(",".join(sels) + "{" + inner + "}")
    return "".join(out)


def escape_angles_in_strings(text):
    out, i, n = [], 0, len(text)
    while i < n:
        if text[i] in "\"'":
            j = skip_string(text, i)
            out.append(text[i:j].replace("<", "\\3c ").replace(">", "\\3e "))
            i = j
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# ПОПРАВКИ ПОД ТИЛЬДУ — дописываются в конец стилей (--no-compat выключает)
# ---------------------------------------------------------------------------
TILDA_COMPAT = [
    # На странице одна обёртка .hits, а в Тильде у каждого блока своя. У .hits
    # position: relative, а позиционированный элемент рисует свой фон поверх
    # предыдущих позиционированных соседей. Розовые пятна секций (::before/::after,
    # z-index: 0, выступают за секцию на 90–160px) уходили под фон следующего
    # блока и обрезались ровно по его границе. static возвращает фон обёртки в слой
    # обычных блоков — под все пятна, как на исходной странице. Относительное
    # позиционирование было нужно только скрытому спрайту иконок размером 0×0.
    ".hits{position:static}",
]

css_min = minify(strip_comments(css))
css_scoped = escape_angles_in_strings(scope_css(css_min))
if COMPAT:
    css_scoped += "".join(TILDA_COMPAT)
if re.search(r"[<>]", css_scoped):
    bad = re.search(r".{0,60}[<>].{0,60}", css_scoped).group(0)
    raise SystemExit(f"В готовом CSS осталась угловая скобка: …{bad}…")


def nbytes(s):
    return len(s.encode("utf-8"))


def split_css(text, limit):
    """Режем по ЦЕЛЫМ верхнеуровневым правилам. @media крупнее куска делим на
    несколько @media с тем же условием подряд — порядок правил не меняется.
    Токены (.hits{--ink…}) идут первыми в файле и попадают в первый блок."""
    blocks = []
    for kind, head, inner in parse_blocks(text):
        if kind == "raw":
            blocks.append(head)
            continue
        whole = head + "{" + inner + "}"
        if kind == "at" and NESTED_AT.match(head) and nbytes(whole) > limit:
            cur = ""
            for k2, h2, i2 in parse_blocks(inner):
                piece = h2 if k2 == "raw" else h2 + "{" + i2 + "}"
                if cur and nbytes(head) + nbytes(cur) + nbytes(piece) + 2 > limit:
                    blocks.append(head + "{" + cur + "}")
                    cur = ""
                cur += piece
            if cur:
                blocks.append(head + "{" + cur + "}")
        else:
            blocks.append(whole)
    parts, cur = [], ""
    for b in blocks:
        if cur and nbytes(cur) + nbytes(b) + 1 > limit:
            parts.append(cur)
            cur = ""
        cur += b + "\n"
    if cur:
        parts.append(cur)
    return parts


def css_capsule(part):
    """CSS, который Тильда не сможет переписать (как в antiotek).

    Тильда переформатирует содержимое блока: она распознала `<svg` внутри
    url(...) как разметку и расставила переносы прямо посреди адреса картинки.
    Поэтому стили отдаём строкой base64: там только латиница и цифры,
    форматировать нечего. Скрипт распаковывает её и кладёт <style> в head.
    """
    b64 = base64.b64encode(part.encode("utf-8")).decode("ascii")
    return (
        "<script>(function(){"
        "var d=\"" + b64 + "\";"
        "var b=atob(d),a=new Uint8Array(b.length),i=0;"
        "for(;i<b.length;i++){a[i]=b.charCodeAt(i);}"
        "var t=(typeof TextDecoder!=='undefined')?new TextDecoder('utf-8').decode(a)"
        ":decodeURIComponent(escape(b));"
        "var s=document.createElement('style');"
        "s.appendChild(document.createTextNode(t));"
        "(document.head||document.documentElement).appendChild(s);"
        "})();</script>\n"
    )


# =========================================================================
# 2. РАЗМЕТКА
# =========================================================================
asset_map = {}
map_file = BASE / "tilda-assets.json"
if map_file.exists():
    asset_map = json.loads(map_file.read_text(encoding="utf-8") or "{}")
else:
    map_file.write_text("{}\n", encoding="utf-8")

bm = re.search(r"<body[^>]*>(.*)</body>", html, re.S | re.I)
if not bm:
    raise SystemExit("Не нашёл <body> в index.html")
body = re.sub(r"<!--.*?-->", "", bm.group(1), flags=re.S)
# внешние подключения больше не нужны — всё внутри блоков
body = re.sub(r'<link[^>]*styles\.css[^>]*>\s*', "", body)
body = re.sub(r'<script[^>]*\bsrc="[^"]*script\.js[^"]*"[^>]*>\s*</script>\s*', "", body)

TAG = re.compile(r"<(/?)([A-Za-z][\w:-]*)((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr"}
RAW = {"script", "style", "textarea", "title"}


def top_nodes(s):
    """Элементы верхнего уровня: (начало, конец откр. тега, начало закр. тега, конец, тег, атрибуты).
    Режем только по целым элементам, поэтому считаем вложенность тегов."""
    out, depth, i, cur = [], 0, 0, None
    while True:
        m = TAG.search(s, i)
        if not m:
            break
        closing, tag, attrs = m.group(1) == "/", m.group(2).lower(), m.group(3)
        if not closing:
            if tag in RAW:
                end = re.compile(r"</%s\s*>" % tag, re.I).search(s, m.end())
                stop = end.end() if end else len(s)
                if depth == 0:
                    out.append((m.start(), m.end(), end.start() if end else stop, stop, tag, attrs))
                i = stop
                continue
            if tag in VOID or attrs.rstrip().endswith("/"):
                if depth == 0:
                    out.append((m.start(), m.end(), m.end(), m.end(), tag, attrs))
            else:
                if depth == 0:
                    cur = (m.start(), m.end(), tag, attrs)
                depth += 1
        else:
            depth -= 1
            if depth < 0:
                raise SystemExit(f"Разметка: лишний </{tag}> около «{s[max(0, m.start() - 80):m.start()]}»")
            if depth == 0:
                out.append((cur[0], cur[1], m.start(), m.end(), cur[2], cur[3]))
        i = m.end()
    if depth:
        raise SystemExit(f"Разметка: не закрыт <{cur[2] if cur else '?'}> — сборщик режет по целым элементам")
    return out


def attr(attrs, name):
    m = re.search(r'(?<![\w-])%s\s*=\s*(?:"([^"]*)"|\'([^\']*)\')' % re.escape(name), attrs)
    if not m:
        return None
    return m.group(1) if m.group(1) is not None else m.group(2)


# Узлы из всех обёрток .hits (сейчас она одна; если станет несколько — тоже годится)
nodes = []
for st, oe, cs, en, tag, attrs in top_nodes(body):
    if tag == "div" and "hits" in (attr(attrs, "class") or "").split():
        inner = body[oe:cs]
        kids = top_nodes(inner)
        for k, (st2, oe2, cs2, en2, tag2, attrs2) in enumerate(kids):
            stop = kids[k + 1][0] if k + 1 < len(kids) else en2
            nodes.append((inner[st2:stop], tag2, attr(attrs2, "id")))
        loose = inner
        for st2, _a, _b, en2, _t, _c in reversed(kids):
            loose = loose[:st2] + loose[en2:]
        if loose.strip():
            warnings.append(f"Текст прямо внутри .hits не попал в блоки: «{loose.strip()[:60]}»")
    elif tag != "script":
        warnings.append(f"Элемент <{tag}> вне .hits не попал в блоки")
    else:
        warnings.append("Посторонний <script> в body не попал в блоки")

known = dict(SECTIONS)
chunks, pending = [], []
for frag, tag, nid in nodes:
    if nid in known or (tag == "section" and nid):
        chunks.append([nid, known.get(nid, nid), "".join(pending) + frag])
        pending = []
    elif chunks:
        chunks[-1][2] += frag
    else:
        pending.append(frag)          # спрайт иконок и всё, что до первой секции
if not chunks:
    raise SystemExit("В разметке не нашлось ни одной секции из списка SECTIONS")
missing_sections = [sid for sid, _ in SECTIONS if sid not in [c[0] for c in chunks]]
if missing_sections:
    warnings.append("Нет секций: " + ", ".join("#" + s for s in missing_sections))


def absolutize(url):
    u = url.strip()
    if not u or re.match(r"^(?:[a-zA-Z][\w+.-]*:|//|#|\?)", u):
        return url
    key = re.sub(r"^\./", "", u).lstrip("/")
    return asset_map.get(key, CDN + "/" + key)


def sub_set(m):
    items = []
    for item in m.group(2).split(","):
        item = item.strip()
        if item:
            bits = item.split(None, 1)
            items.append(absolutize(bits[0]) + ((" " + bits[1]) if len(bits) > 1 else ""))
    return f'{m.group(1)}="' + ", ".join(items) + '"'


def fix_urls(fragment):
    # poster у видео — такой же адрес ресурса, как src (antiotek). ЗДЕСЬ добавлены
    # места под медиа: относительный путь в data-video/-audio/-photo тоже уводим на CDN.
    fragment = re.sub(r'(?<![\w-])(src|poster|data-video|data-audio|data-photo)="([^"]*)"',
                      lambda m: f'{m.group(1)}="{absolutize(m.group(2))}"', fragment)
    fragment = re.sub(r'(?<![\w-])(href)="((?:\./)?assets/[^"]*)"',
                      lambda m: f'{m.group(1)}="{absolutize(m.group(2))}"', fragment)
    return re.sub(r'(?<![\w-])(srcset|imagesrcset)="([^"]*)"', sub_set, fragment)


def to_entities(text):
    # анти-кракозябры: Тильда пересохраняет блок и портит не-ASCII
    return "".join(c if ord(c) < 128 else f"&#{ord(c)};" for c in text)


def wrap_markup(fragment):
    return '<div class="hits">\n' + to_entities(fragment) + '\n</div>\n'


def fits(fragment):
    return len(wrap_markup(fragment)) <= MARKUP_LIMIT


def split_markup(frag, pre="", post=""):
    """Секция не влезла в блок — делим по крупным дочерним узлам. Предки
    повторяются в каждой части, id остаётся только в первой. Дерево при этом
    уже не то же самое (две секции вместо одной), поэтому сборщик предупреждает."""
    if fits(pre + frag + post):
        return [pre + frag + post]
    ns = top_nodes(frag)
    if len(ns) == 1:
        st, oe, cs, en, tag, _attrs = ns[0]
        if oe == cs:
            raise SystemExit(f"Узел <{tag}> один больше лимита блока — резать нечего")
        o = frag[st:oe]
        res = split_markup(frag[oe:cs], pre + frag[:st] + o, frag[cs:] + post)
        head = pre + frag[:st] + o
        naked = pre + frag[:st] + re.sub(r'\s+id="[^"]*"', "", o)
        return [res[0]] + [naked + r[len(head):] for r in res[1:]]
    if not ns:
        raise SystemExit("Текстовый фрагмент больше лимита блока — резать нечего")
    pieces, prev = [], 0
    for k, (st, _oe, _cs, en, _t, _a) in enumerate(ns):
        stop = en if k + 1 < len(ns) else len(frag)
        pieces.append(frag[prev:stop])
        prev = stop
    groups, cur = [], ""
    for p in pieces:
        if cur and not fits(pre + cur + p + post):
            groups.append(cur)
            cur = ""
        cur += p
    groups.append(cur)
    out = []
    for g in groups:
        out.extend(split_markup(g, pre, post))
    return out


# =========================================================================
# 3. СКРИПТ
# =========================================================================
def js_for_tilda(text):
    r"""JS, безопасный для вставки в блок Тильды (как в antiotek).

    Тильда пересохраняет содержимое блока и портит не-ASCII. HTML-сущности тут не
    годятся: внутри <script> они не декодируются. Поэтому комментарии срезаем, а
    кириллицу в коде переводим в \uXXXX. Комментарии режем посимвольно, а не
    регуляркой: «//» встречается внутри строк с адресами (https://...).
    """
    out, i, n = [], 0, len(text)
    quote = None
    while i < n:
        c = text[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "'\"`":
            quote = c
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        out.append(c)
        i += 1
    code = "".join(out)
    code = re.sub(r"[ \t]+\n", "\n", code)
    code = re.sub(r"\n{3,}", "\n\n", code)
    code = code.replace("</", "<\\/")     # «</script>» в строке закрыл бы блок раньше времени
    return "".join(ch if ord(ch) < 128 else "\\u%04x" % ord(ch) for ch in code)


def check_js(code):
    """ЗДЕСЬ добавлено: посимвольная резка комментариев не знает про регулярки
    JS. Прогоняем результат через node --check — битый скрипт не уедет в Тильду."""
    node = shutil.which("node")
    if not node:
        warnings.append("node не найден — синтаксис скрипта после чистки не проверен")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = Path(f.name)
    try:
        r = subprocess.run([node, "--check", str(tmp)], capture_output=True, text=True)
    finally:
        tmp.unlink()
    if r.returncode:
        raise SystemExit("Скрипт после чистки не проходит node --check:\n" + r.stderr)


js_safe = js_for_tilda(js)
check_js(js_safe)


# =========================================================================
# 4. СБОРКА БЛОКОВ
# =========================================================================
files = []          # (сырое имя, подпись для человека, содержимое)
head = ('<link rel="preconnect" href="https://fonts.googleapis.com" />\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />\n'
        f'{FONT_LINK}\n')
style_parts = split_css(css_scoped, CSS_CHUNK)
for k, part in enumerate(style_parts, 1):
    files.append((f"style-{k}.html", f"стили, часть {k}", (head if k == 1 else "") + css_capsule(part)))

mk = 0
for sid, label, frag in chunks:
    parts = split_markup(fix_urls(frag))
    if len(parts) > 1:
        warnings.append(f"Секция #{sid} не влезла в один блок — разрезана на {len(parts)}: "
                        "дерево разметки поменялось, проверьте вёрстку глазами")
    for k, p in enumerate(parts, 1):
        mk += 1
        tail = f"-{k}" if len(parts) > 1 else ""
        files.append((f"markup-{mk}-{sid}{tail}.html",
                      f"разметка, {label}" + (f", часть {k}" if len(parts) > 1 else ""),
                      wrap_markup(p)))

files.append(("script.html", "скрипт (вставлять последним)", "<script>\n" + js_safe + "\n</script>\n"))

over = [f"{name}: {len(c):,}" for name, _h, c in files if len(c) >= LIMIT]
if over:
    raise SystemExit("Блоки больше лимита Тильды: " + "; ".join(over))

all_markup = "".join(c for n, _h, c in files if n.startswith("markup-"))
if re.search(r"<img(?![^>]*\ssrc=)[^>]*>", all_markup):
    # на Тильде действует img:not([src]){visibility:hidden}
    warnings.append("Есть <img> без src — Тильда такие скрывает (img:not([src]))")

OUT.mkdir(exist_ok=True)
for stale in OUT.glob("*.html"):          # от прошлых сборок могли остаться лишние блоки
    stale.unlink()
for name, _h, content in files:
    (OUT / name).write_text(content, encoding="utf-8")

# ---------- папка «ДЛЯ ТИЛЬДЫ» — то, что уходит человеку -------------------
# Имена с номерами задают порядок вставки, инструкция генерируется тут же:
# один пропущенный при ручном копировании файл — и на страницу уезжала
# половина старой сборки (antiotek).
HAND.mkdir(exist_ok=True)
for old in HAND.glob("*.html"):
    old.unlink()
human_names = []
for n, (name, human, content) in enumerate(files, 1):
    hn = f"{n:02d} — {human}"
    (HAND / f"{hn}.html").write_text(content, encoding="utf-8")
    human_names.append((hn, content))

cdn_urls = sorted(set(re.findall(re.escape(CDN) + r"/[^\s\"',]+", all_markup)))

slot_lines = []
for a, what in SLOT_ATTRS:
    where = [f"«{hn}» — {len(re.findall(r'(?<![\w-])' + a + '=', c))} шт."
             for hn, c in human_names if re.search(r'(?<![\w-])' + a + '=', c)]
    if where:
        slot_lines.append(f"  {a} — {what}: " + "; ".join(where))
    else:
        slot_lines.append(f"  {a} — {what}: в текущей разметке мест пока нет, появятся после пересборки")

slots_md = BASE / "SLOTS.md"
slots_extra = ""
if slots_md.exists():
    txt = slots_md.read_text(encoding="utf-8")
    txt = re.sub(r"(?m)^#+\s*", "", txt)
    txt = txt.replace("**", "").replace("`", "")
    slots_extra = "\nПодробно (из SLOTS.md):\n" + "\n".join("  " + ln if ln.strip() else "" for ln in txt.strip().splitlines()) + "\n"

readme = f"""ШАГАЙ ПОД ХИТЫ — блоки для Тильды
=================================

1. Каждый файл — отдельный блок T123 «HTML-код». Вставлять сверху вниз,
   в порядке номеров: стили первыми, скрипт последним.

{chr(10).join("   " + hn + ".html" for hn, _c in human_names)}

2. Блоки от прошлой сборки удалить полностью и только потом вставить новые.
   Не вставлять поверх и не смешивать старые блоки с новыми.

3. В настройках страницы не должно быть своих отступов у блоков: если у блока
   есть поля «отступ сверху/снизу» — поставить 0. Все отступы уже заложены
   внутри блоков, лишние дадут полосы между секциями.

Места под медиа — ссылка вписывается в кавычки атрибута прямо в коде блока
(например data-video="https://…"):
{chr(10).join(slot_lines)}
{slots_extra}
Картинки ({len(cdn_urls)} шт.) пока грузятся с GitHub. Загрузите их в Тильду
и пришлите ссылки — они подставятся пересборкой, и внешних адресов на
странице не останется.

Стили внутри блоков записаны закодированной строкой, а русские буквы в
скрипте — кодами: Тильда переформатирует содержимое блоков и иначе портит
и то, и другое.
"""
(HAND / "ПРОЧТИ ПЕРВЫМ.txt").write_text(readme, encoding="utf-8")

# ---------- предпросмотр: блоки в обёртках, как на опубликованной Тильде ------
# Разметка обёрток — из выгрузки страницы Тильды (rec → t123 → t-container_100 →
# t-width_100). Кроме tilda-grid, у опубликованной страницы есть общий CSS:
# ссылки, списки, картинки без src. Его глобальные правила — снимком ниже,
# чтобы предпросмотр ловил те же конфликты, что и прод.
TILDA_PAGE_CSS = (
    ".t-body{margin:0}body{background-color:#fff}"
    ".t-records{-webkit-font-smoothing:antialiased;background-color:#fff}"
    ":where(.t-records) a,:where(.t-records) button{outline:none}"
    ":where(.t-records) a{color:#1f1300;text-decoration:none}"
    ":where(.t-records) ol{padding-left:22px;margin-top:0;margin-bottom:10px}"
    ":where(.t-records) ul{padding-left:20px;margin-top:0;margin-bottom:10px}"
    ":where(.t-records) b,:where(.t-records) strong{font-weight:700}"
    "img:not([src]){visibility:hidden}"
)
recs = []
for k, (_name, _human, content) in enumerate(files, 1):
    recs.append(
        f'<div id="rec{900000000 + k}" class="r t-rec" style=" " data-animationappear="off" '
        'data-record-type="131"><!-- T123 --><div class="t123"><div class="t-container_100 ">'
        '<div class="t-width t-width_100 "><!-- nominify begin -->\n'
        + content + '<!-- nominify end --></div></div></div></div>')
preview = (
    '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    '<title>Шагай под хиты — предпросмотр блоков Тильды</title>'
    '<link rel="stylesheet" href="https://static.tildacdn.com/css/tilda-grid-3.0.min.css" type="text/css" media="all">'
    '<style>' + TILDA_PAGE_CSS + '</style></head>'
    '<body class="t-body" style="margin:0;">'
    '<div id="allrecords" class="t-records" data-hook="blocks-collection-content-node">\n'
    + "\n".join(recs) + "\n</div></body></html>\n")
PREVIEW.parent.mkdir(exist_ok=True)
PREVIEW.write_text(preview, encoding="utf-8")

# ---------- отчёт ---------------------------------------------------------
print(f"CSS: {nbytes(css) / 1024:.1f} КБ -> {nbytes(css_scoped) / 1024:.1f} КБ после чистки и префикса {SCOPE}"
      f"; частей: {len(style_parts)}; поправки под Тильду: {'да' if COMPAT else 'ВЫКЛЮЧЕНЫ (--no-compat)'}")
print(f"Дочерний комбинатор переписан в {len(child_rewrites)} селекторах: "
      + "; ".join(s.strip() for s in child_rewrites))
print(f"\nГотово -> {HAND}")
for hn, content in human_names:
    n = len(content)
    print(f"  {hn + '.html':48} {n:>7,} знаков  {'OK' if n < LIMIT else '!! ЛИМИТ'}")
print(f"\nКартинок с GitHub: {len(cdn_urls)} (адреса Тильды — в tilda-assets.json)")
print(f"Предпросмотр: {PREVIEW.relative_to(BASE)}")
for w in warnings:
    print("!!", w)
