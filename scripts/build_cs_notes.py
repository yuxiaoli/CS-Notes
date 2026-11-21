#!/usr/bin/env python3
"""Build the fork's standalone Pages site from the local upstream checkout."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from html import escape, unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
import unicodedata
from urllib.parse import quote, unquote, urlsplit

SITE_TITLE = "计算机学习笔记"
FORK = "https://github.com/yuxiaoli/CS-Notes"
UPSTREAM = "https://github.com/CyC2018/CS-Notes"
CREDIT = '<span>Adapted by <a href="https://s.vectorindex.cloud/sean">Sean</a> with ❤️</span>'
EXCLUDED = {"攻击技术.md"}
ASSET_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif", ".svg", ".ico", ".pdf"}
TOPICS = {
    "路线": ("学习路线", ("学习路线",)),
    "算法": ("算法与题解", ("算法", "Leetcode", "剑指 Offer", "数据结构")),
    "系统": ("操作系统与网络", ("计算机操作系统", "Linux", "计算机网络", "HTTP", "Socket")),
    "数据库": ("数据库", ("数据库", "SQL", "MySQL", "Redis", "Elasticsearch")),
    "Java": ("Java 与框架", ("Java", "Spring")),
    "设计": ("系统设计与 AI", ("系统设计", "分布式", "集群", "微服务", "缓存", "消息队列", "大模型", "面向对象", "设计模式")),
    "工具": ("工程工具", ("Git", "Docker", "构建工具", "Maven")),
}
TAG_URL = re.compile(r'(?P<name>href|src)="(?P<value>[^"]*)"', re.I)
HEADINGS = re.compile(r'<h([1-6]) id="([^"]+)">(.*?)</h\1>', re.S)
TAGS = re.compile(r'<[^>]+>')
VALID_BASE = re.compile(r"/(?:[A-Za-z0-9._~/-]+/)?")
SAFE_OUTPUT = "cs-notes-pages-dist"
STYLES = ("style.css", "search.js")


def em(value: str) -> str:
    return escape(value, quote=True)


def name_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:16]


def normalized(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()


def discover(root: Path) -> dict[str, Path]:
    notes = (root / "notes").resolve()
    if not notes.is_dir() or root.resolve() not in notes.parents:
        raise ValueError("Expected local notes/ source directory")
    pages = {p.relative_to(root).as_posix(): p for p in sorted(notes.rglob("*.md"))
             if p.name not in EXCLUDED and not p.is_symlink() and notes in p.resolve().parents}
    if not pages:
        raise ValueError("No publishable Markdown notes found")
    return pages


def render_md(path: Path) -> str:
    return subprocess.run(["pandoc", "--from=gfm-raw_html", "--to=html5", "--wrap=none"],
                          input=path.read_text(encoding="utf-8-sig"), text=True,
                          encoding="utf-8", capture_output=True, check=True, timeout=30).stdout


def relative_link(src: str, target: str) -> str:
    return posixpath.relpath(target, posixpath.dirname(src) or ".")


def article_source(src: str) -> str:
    return f"{UPSTREAM}/blob/master/{quote(src, safe='/')}"


def category(source: str) -> str:
    title = Path(source).stem
    for label, terms in TOPICS.values():
        if any(title.startswith(term) for term in terms):
            return label
    return "更多笔记"


def asset_index(root: Path) -> dict[str, list[Path]]:
    assets: dict[str, list[Path]] = {}
    for parent in (root / "notes" / "pics", root / "assets", root / "docs" / "_media"):
        for p in parent.rglob("*"):
            if p.is_file() and not p.is_symlink() and p.suffix.lower() in ASSET_SUFFIXES and root in p.resolve().parents:
                assets.setdefault(p.name, []).append(p)
    return assets


def collect_asset(path: Path, root: Path, out: Path) -> str | None:
    if (not path.is_file() or path.is_symlink() or root not in path.resolve().parents
            or path.suffix.lower() not in ASSET_SUFFIXES):
        return None
    target = f"media/{name_hash(path.relative_to(root).as_posix())}{path.suffix.lower()}"
    out_asset = out / target
    out_asset.parent.mkdir(parents=True, exist_ok=True)
    if not out_asset.exists():
        shutil.copyfile(path, out_asset)
    return target


def mapped_url(raw: str, src: str, dest: str, routes: dict[str, str], root: Path, out: Path,
               assets: dict[str, list[Path]], image: bool) -> str | None:
    raw = unescape(raw).strip()
    if not raw or re.search(r"[\x00-\x1f\x7f\\]", raw) or raw.startswith("//"):
        return None
    try:
        u = urlsplit(raw)
    except ValueError:
        return None
    raw_path = unquote(u.path)
    if Path(raw_path).name in EXCLUDED:
        return None
    suffix = f"#{quote(unquote(u.fragment), safe='-_.~')}" if u.fragment else ""
    if not u.path and not u.scheme:
        return suffix or None
    if u.scheme:
        if u.scheme not in {"https", "http", "mailto"}:
            return None
        if u.hostname == "github.com" and raw_path.startswith("/CyC2018/CS-Notes/blob/master/"):
            candidate = raw_path.removeprefix("/CyC2018/CS-Notes/blob/master/")
            if candidate in routes:
                return relative_link(dest, routes[candidate]) + suffix
        if image and u.hostname and u.hostname.endswith(".myqcloud.com"):
            matches = assets.get(Path(raw_path).name, [])
            if len(matches) == 1:
                target = collect_asset(matches[0], root, out)
                if target:
                    return relative_link(dest, target)
        return raw
    candidate = posixpath.normpath(posixpath.join(posixpath.dirname(src), raw_path))
    if raw_path.startswith("/") or candidate.startswith("../"):
        return None
    if candidate in routes:
        return relative_link(dest, routes[candidate]) + suffix
    if candidate.lower().endswith(".md"):
        return article_source(candidate) if (root / candidate).is_file() else None
    target = collect_asset(root / candidate, root, out)
    return (relative_link(dest, target) + suffix) if target else None


class ArticleSanitizer(HTMLParser):
    ALLOWED = set("a abbr b blockquote br caption code dd del details div dl dt em figcaption figure "
                  "h1 h2 h3 h4 h5 h6 hr i img kbd li mark ol p pre s samp small span strong sub summary "
                  "sup table tbody td th thead tr u ul var wbr".split())
    BLOCKED = {"script", "style", "object", "iframe", "embed", "video", "audio", "form", "template"}
    VOID = {"br", "hr", "img", "wbr"}

    def __init__(self, link):
        super().__init__(convert_charrefs=False)
        self.link, self.chunks, self.skip = link, [], []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCKED:
            if tag != "embed":
                self.skip.append(tag)
            return
        if self.skip or tag not in self.ALLOWED:
            return
        output_tag = "h2" if tag == "h1" else tag
        def arg(key, value):
            return f' {key}="{em(value)}"'
        args = []
        for key, value in attrs:
            if value is None:
                continue
            if (tag == "a" and key == "href") or (tag == "img" and key == "src"):
                value = self.link(value, key == "src")
                if value:
                    args.append(arg(key, value))
            elif key in {"id", "class", "title", "alt", "lang"} and len(value) <= 512:
                args.append(arg(key, value))
            elif key in {"colspan", "rowspan", "width", "height", "start"} and re.fullmatch(r"\d{1,4}", value):
                args.append(arg(key, value))
        if tag == "img":
            if not any(attr.startswith(" src=") for attr in args):
                alt = dict(attrs).get("alt") or ""
                self.chunks.append(escape(alt))
                return
            args.extend([arg("loading", "lazy"), arg("decoding", "async")])
        self.chunks.append(f'<{output_tag}{"".join(args)}>')

    def handle_startendtag(self, tag, attrs):
        if tag in self.BLOCKED:
            return
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.skip:
            if self.skip[-1] == tag:
                self.skip.pop()
            return
        if tag in self.ALLOWED and tag not in self.VOID:
            self.chunks.append(f'</{"h2" if tag == "h1" else tag}>')

    def handle_data(self, data):
        if not self.skip:
            self.chunks.append(escape(data))

    def handle_entityref(self, name):
        if not self.skip:
            self.chunks.append(f"&{name};")

    def handle_charref(self, name):
        if not self.skip:
            self.chunks.append(f"&#{name};")


def article_html(html: str, src: str, dest: str, routes: dict[str, str], root: Path, out: Path,
                 assets: dict[str, list[Path]]) -> str:
    parser = ArticleSanitizer(lambda url, image: mapped_url(url, src, dest, routes, root, out, assets, image))
    parser.feed(html)
    parser.close()
    return "".join(parser.chunks)


def shell(title: str, dest: str, base: str, revision: str, content: str) -> str:
    root = relative_link(dest, "index.html")
    css = relative_link(dest, "assets/style.css")
    script = relative_link(dest, "assets/search.js")
    canonical = f"https://yuxiaoli.github.io{base}{dest}".removesuffix("index.html")
    html_title = title if title == SITE_TITLE else f"{title} | {SITE_TITLE}"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{em(html_title)}</title><link rel="canonical" href="{em(canonical)}">
<meta name="description" content="按主题阅读计算机基础、编程和系统学习笔记。"><link rel="stylesheet" href="{em(css)}">
<script defer src="{em(script)}"></script></head><body>
<a class="skip" href="#main">跳到正文</a><header class="top"><div class="top-inner"><a class="brand" href="{em(root)}"><svg viewBox="0 0 24 24" aria-hidden="true" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1zm0 0v15"/></svg>{SITE_TITLE}</a>
<nav aria-label="主导航"><a href="{em(root)}#topics">浏览主题</a><a href="{FORK}">GitHub 仓库 <span aria-hidden="true">↗</span></a></nav></div></header>
<main id="main">{content}</main>
<footer><div><p>{CREDIT}</p><p>内容来源：<a href="{UPSTREAM}">CyC2018 和贡献者</a> · <a href="{UPSTREAM}#license">原项目许可</a></p></div><code title="构建来源提交">{em(revision[:12])}</code></footer></body></html>"""


def topic_id(label: str) -> str:
    return f"topic-{name_hash(label)}"


def topic_nav(labels: list[str], home_url: str, current: str = "") -> str:
    links = []
    for label in labels:
        state = ' class="selected"' if label == current else ""
        links.append(f'<li><a{state} href="{home_url}#{topic_id(label)}">{em(label)}</a></li>')
    return '<nav class="topic-nav" aria-label="按主题浏览"><p>主题</p><ul>' + "".join(links) + '</ul></nav>'


def home(pages: dict[str, Path], routes: dict[str, str], labels: list[str]) -> str:
    buckets: dict[str, list[str]] = {label: [] for label in labels}
    for src in pages:
        label, title = category(src), Path(src).stem
        buckets[label].append(
            f'<li data-title="{em(normalized(title))}"><a href="{routes[src]}">{em(title)}</a></li>')
    sections = ''.join(
        f'<section class="topic" id="{topic_id(label)}" data-topic><h3>{em(label)}</h3><ul>{"".join(items)}</ul></section>'
        for label, items in buckets.items())
    return f"""<div class="home-layout">{topic_nav(labels, '')}<div class="home-main"><header class="home-intro">
<h1>{SITE_TITLE}</h1><p>查阅算法、计算机系统、网络、数据库和编程语言笔记。</p>
<div class="search" hidden><label for="search">搜索笔记</label><div class="search-field"><svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="6.75" cy="6.75" r="4.5"/><path d="m10 10 3.7 3.7"/></svg>
<input id="search" type="search" placeholder="例如：数据库、Java、网络" autocomplete="off" aria-controls="topic-grid"></div></div></header>
<section id="topics" aria-labelledby="topics-title"><h2 id="topics-title">浏览主题</h2>
<p id="search-status" role="status" aria-live="polite"></p><div class="grid" id="topic-grid">{sections}</div></section></div></div>"""


def note_page(src: str, body: str, dest: str, labels: list[str]) -> str:
    title, label = Path(src).stem, category(src)
    root = relative_link(dest, "index.html")
    groups = [(level, anchor, unescape(TAGS.sub("", caption)))
              for level, anchor, caption in HEADINGS.findall(body) if int(level) <= 4]
    toc_items = "".join(f'<li class="level-{level}"><a href="#{em(anchor)}">{em(caption)}</a></li>'
                        for level, anchor, caption in groups)
    toc = f'<div class="outline"><details open><summary>本页目录</summary><nav aria-label="本页目录"><ul>{toc_items}</ul></nav></details></div>' if toc_items else ""
    layout = "reading with-outline" if toc else "reading"
    return f"""<div class="note-layout">{topic_nav(labels, root, label)}<div class="note-main">
<nav class="crumb" aria-label="页面路径"><ol><li><a href="{root}">首页</a></li><li><a href="{root}#{topic_id(label)}">{em(label)}</a></li><li aria-current="page">{em(title)}</li></ol></nav>
<div class="{layout}"><div class="article-heading"><h1 id="article-title">{em(title)}</h1></div>{toc}
<article aria-labelledby="article-title"><div class="prose">{body}</div>
<p class="source">原文：<a href="{article_source(src)}">CyC2018/CS-Notes ↗</a> ·
<a href="{UPSTREAM}#license">署名及相同方式共享</a></p></article></div></div></div>"""


class PageIDs(HTMLParser):
    def __init__(self, value: str):
        super().__init__()
        self.ids: set[str] = set()
        self.feed(value)

    def handle_starttag(self, tag, attributes):
        self.ids.update(value for name, value in attributes if name == "id" and value)


def section_key(value: str) -> str:
    return "".join(ch for ch in normalized(unquote(value)) if ch.isalnum())


def validate_and_repair_links(out: Path) -> tuple[int, int]:
    html = {p: p.read_text(encoding="utf-8") for p in out.rglob("*.html")}
    anchors = {p: PageIDs(value).ids for p, value in html.items()}
    heading_aliases = {p: [(section_key(unescape(TAGS.sub('', label))), anchor)
                           for _, anchor, label in HEADINGS.findall(value)]
                       for p, value in html.items()}
    resolved = downgraded = 0
    for source, value in html.items():
        def fix(m):
            nonlocal resolved, downgraded
            url = urlsplit(unescape(m["value"]))
            if url.scheme or url.netloc:
                return m[0]
            target = (source.parent / unquote(url.path)).resolve() if url.path else source
            if out not in target.parents or not target.is_file():
                raise ValueError(f"Missing generated target: {source.relative_to(out)}")
            if not url.fragment or target not in anchors or unquote(url.fragment) in anchors[target]:
                return m[0]
            key = section_key(url.fragment)
            match = {i for i in anchors[target] if key and section_key(i) == key}
            match.update(anchor for alias, anchor in heading_aliases[target] if key and alias == key)
            if len(match) == 1:
                resolved += 1
                fragment = "#" + quote(next(iter(match)), safe="-_.~")
            else:
                # The imported renderer uses a different section ID scheme; keep the note link.
                downgraded += 1
                fragment = "#main"
            return f'{m["name"]}="{em(url.path + fragment)}"'
        value = TAG_URL.sub(fix, value)
        source.write_text(value, encoding="utf-8")
    return resolved, downgraded


def revision_for(root: Path) -> str:
    value = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
    rev = value.stdout.strip() if value.returncode == 0 else "local"
    return rev if re.fullmatch(r"[0-9a-f]{40}|local", rev) else "local"


def build(root: Path, out: Path, base: str) -> int:
    root, out = root.resolve(), out.resolve()
    if not VALID_BASE.fullmatch(base) or any(x in {".", ".."} for x in base.split("/")):
        raise ValueError("Site base must be root-relative with a trailing slash")
    if out == root or out in root.parents or out.name != SAFE_OUTPUT or out.exists():
        raise ValueError(f"Output must be a new directory named {SAFE_OUTPUT}; preserve previous output")
    pages = discover(root)
    routes = {src: f"notes/{name_hash(src)}.html" for src in pages}
    assets = asset_index(root)
    present = {category(src) for src in pages}
    labels = [label for label in [*(label for label, _ in TOPICS.values()), "更多笔记"] if label in present]
    rev = revision_for(root)
    out.mkdir(parents=True)
    (out / "notes").mkdir()
    (out / "assets").mkdir()
    for filename in STYLES:
        shutil.copyfile(Path(__file__).with_name("cs_notes_site") / filename, out / "assets" / filename)
    (out / ".nojekyll").touch()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = pool.map(render_md, pages.values())
        for src, body in zip(pages, results):
            dest = routes[src]
            body = article_html(body, src, dest, routes, root, out, assets)
            (out / dest).write_text(shell(Path(src).stem, dest, base, rev, note_page(src, body, dest, labels)), encoding="utf-8")
    (out / "index.html").write_text(shell(SITE_TITLE, "index.html", base, rev, home(pages, routes, labels)), encoding="utf-8")
    (out / "404.html").write_text(shell("未找到笔记", "404.html", base, rev,
                                        '<h1>未找到笔记</h1><p><a href="index.html">浏览所有主题</a></p>'), encoding="utf-8")
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' +
        "".join(f"<url><loc>https://yuxiaoli.github.io{base}{target}</loc></url>"
                for target in ["", *routes.values()]) + "</urlset>", encoding="utf-8")
    resolved, downgraded = validate_and_repair_links(out)
    print(f"Validated local links; resolved {resolved} legacy anchors, kept {downgraded} at note level.")
    return len(pages)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, default=Path(SAFE_OUTPUT))
    parser.add_argument("--base", default="/CS-Notes/")
    args = parser.parse_args()
    count = build(args.source, args.out, args.base)
    print(f"Built {count} notes in {args.out}.")


if __name__ == "__main__":
    main()
