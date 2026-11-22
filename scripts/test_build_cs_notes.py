from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import urlsplit
from html.parser import HTMLParser
from xml.etree import ElementTree

from build_cs_notes import build, mapped_url, section_key


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.links += [value for key, value in attrs if key in {"href", "src"} and value]


class BuildTest(unittest.TestCase):
    def test_preserves_public_input_and_works_under_pages_path(self):
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            root = tmp / "source"
            notes = root / "notes"
            pics = notes / "pics"
            pics.mkdir(parents=True)
            a = notes / "计算机网络.md"
            a.write_text('# 可见标题\n\n[下一篇](Java%20词条.md#异结-论)\n\n'
                         '<div align="center"><img src="pics/sample.png" alt="网络图"/></div>\n\n'
                         '   sample code\n\n<script>alert(1)</script>\n\n'
                         '[不安全链接](javascript:alert%281%29)\n\n[省略的条目](攻击技术.md)\n', encoding="utf-8")
            b = notes / "Java 词条.md"
            b.write_text('## 异结、论\n\n[返回](计算机网络.md)\n', encoding="utf-8")
            (notes / "攻击技术.md").write_text("NOT_PUBLISHED", encoding="utf-8")
            (pics / "sample.png").write_bytes(b"example-image-fixture")
            before = {p: p.read_bytes() for p in notes.rglob("*") if p.is_file()}
            out = tmp / "cs-notes-pages-dist"
            self.assertEqual(build(root, out, "/CS-Notes/"), 2)
            self.assertEqual(before, {p: p.read_bytes() for p in before})
            self.assertEqual(len(list((out / "media").glob("*.png"))), 1)
            self.assertEqual((out / "assets/computer-mark.png").read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(len(ElementTree.parse(out / "sitemap.xml").getroot()), 3)
            for path in out.rglob("*.html"):
                content = path.read_text(encoding="utf-8")
                self.assertIn('Adapted by <a href="https://s.vectorindex.cloud/sean">Sean</a> with ❤️', content)
                self.assertIn('href="https://github.com/yuxiaoli/CS-Notes"', content)
                self.assertRegex(content, r'<link rel="icon" href="[^"]*assets/computer-mark\.png\?v=[^"]+" type="image/png">')
                self.assertRegex(content, r'<img class="brand-mark" src="[^"]*assets/computer-mark\.png\?v=[^"]+"')
                self.assertNotIn("NOT_PUBLISHED", content)
                self.assertNotIn('<script>alert', content)
                if path.parent.name == "notes":
                    self.assertIn("/CyC2018/CS-Notes/blob/master/notes/", content)
                parser = Links()
                parser.feed(content)
                for link in parser.links:
                    parsed = urlsplit(link)
                    if not parsed.scheme and parsed.path:
                        self.assertTrue((path.parent / parsed.path).exists(), f"Missing {link} in {path.name}")
                self.assertNotIn("javascript:", [urlsplit(link).scheme + ":" for link in parser.links])
            with self.assertRaisesRegex(ValueError, "new directory"):
                build(root, out, "/CS-Notes/")

    def test_rejects_unsafe_urls_and_hides_excluded_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for raw in ("javascript:foo", "file:/tmp/a", "//example.test/a", "../../etc/passwd", "攻击技术.md"):
                self.assertIsNone(mapped_url(raw, "notes/a.md", "notes/a.html", {}, root, root, {}, False))

    def test_matches_upstream_and_pandoc_fragment_styles(self):
        self.assertEqual(section_key('一、三大特性'), section_key('一-三大特性'))
