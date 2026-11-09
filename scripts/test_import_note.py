from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import BadZipFile, ZipFile

from build import NoteParser
from import_note import import_note


HTML = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>Физиология &amp; клетка</title></head><body>
<nav>Навигация</nav><section id="cell"><h2>Клеточная мембрана</h2>
<p>Через неё проходят ионы.</p><script>const secret = 1;</script>
</section></body></html>"""


class ImportNoteTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.notes = self.root / "notes"
        target = patch("import_note.NOTES", self.notes)
        target.start()
        self.addCleanup(target.stop)

    def test_html_search_data_duplicate_and_conflict(self):
        source = self.root / "input.html"
        source.write_text(HTML, encoding="utf-8")
        import_note(source, "Физиология", "cell")
        imported = self.notes / "cell" / "content" / "index.html"
        self.assertEqual(imported.read_bytes(), source.read_bytes())
        parser = NoteParser.read(imported)
        self.assertEqual(parser.title, "Физиология & клетка")
        self.assertEqual(parser.sections, [{
            "heading": "Клеточная мембрана", "anchor": "cell",
            "text": "Через неё проходят ионы.",
        }])
        import_note(source, "Физиология", "cell")
        import_note(source, "Физиология", "same-content")
        source.write_text(HTML.replace("мембрана", "стенка"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "уже занят"):
            import_note(source, "Физиология", "cell")
        self.assertEqual(list(self.notes.iterdir()), [self.notes / "cell"])

    def test_zip_keeps_assets(self):
        source = self.root / "input.zip"
        with ZipFile(source, "w") as archive:
            archive.writestr("index.html", HTML)
            archive.writestr("img/figure.jpg", b"figure")
        import_note(source, "Физиология", "cell")
        image = self.notes / "cell" / "content" / "img" / "figure.jpg"
        self.assertEqual(image.read_bytes(), b"figure")

    def test_zip_cannot_write_outside_import(self):
        source = self.root / "input.zip"
        for path in ("../escaped.svg", "C:/escaped.svg", "img\\escaped.svg", "img/file.jpg:stream"):
            with self.subTest(path=path):
                with ZipFile(source, "w") as archive:
                    archive.writestr("index.html", HTML)
                    archive.writestr(path.replace("\\", "/"), b"invalid")
                if "\\" in path:
                    source.write_bytes(source.read_bytes().replace(
                        path.replace("\\", "/").encode(), path.encode()
                    ))
                with self.assertRaises(ValueError):
                    import_note(source, "Физиология", "cell")
                self.assertEqual(list(self.notes.iterdir()), [])

    def test_corrupt_zip_leaves_catalog_unchanged(self):
        source = self.root / "input.zip"
        source.write_bytes(b"broken")
        with self.assertRaises(BadZipFile):
            import_note(source, "Физиология", "cell")
        self.assertEqual(list(self.notes.iterdir()), [])

    def test_title_in_body_matches_existing_notes(self):
        source = self.root / "input.html"
        source.write_text(HTML.replace("<title>", "</head><body><title>")
                          .replace("</title></head><body>", "</title>"), encoding="utf-8")
        import_note(source, "Физиология", "cell")
        parser = NoteParser.read(self.notes / "cell" / "content" / "index.html")
        self.assertEqual(parser.title, "Физиология & клетка")
        self.assertEqual(len(parser.sections), 1)
