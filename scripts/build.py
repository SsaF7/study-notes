"""Generate a static library and a search index from imported notes."""

from contextlib import contextmanager
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / "notes"
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
IGNORED = {"script", "style", "template", "noscript", "nav"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}


@contextmanager
def staging_directory(parent, prefix):
    parent = parent.resolve()
    staging = parent / f"{prefix}{uuid4().hex}"
    # Published directories keep their inherited Windows ACL when renamed.
    staging.mkdir()
    try:
        yield staging
    finally:
        if staging.resolve() != staging:
            raise ValueError("Временная папка была перенаправлена.")
        shutil.rmtree(staging)


class NoteParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.sections = []
        self.stack = []
        self.heading = ""
        self.anchor = ""
        self.parts = []

    @classmethod
    def read(cls, file):
        parser = cls()
        parser.feed(file.read_text(encoding="utf-8-sig"))
        parser.close()
        parser.finish_section()
        parser.title = " ".join(parser.title.split())
        return parser

    def finish_section(self):
        body = " ".join(" ".join(self.parts).split())
        if body or self.heading:
            self.sections.append({"heading": self.heading, "anchor": self.anchor, "text": body})
        self.parts.clear()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in VOID:
            return
        self.stack.append((tag, attrs.get("id") or ""))
        tags = {name for name, _ in self.stack}
        if tag in HEADINGS and "body" in tags and not tags.intersection(IGNORED):
            self.finish_section()
            self.heading = ""
            self.anchor = next((anchor for _, anchor in reversed(self.stack) if anchor), "")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        tags = {tag for tag, _ in self.stack}
        if tags.intersection(IGNORED):
            return
        if "title" in tags:
            self.title += data
        elif "body" in tags:
            if tags.intersection(HEADINGS):
                self.heading = " ".join((self.heading + data).split())
            elif data.strip():
                self.parts.append(data)


def write_json(file, value):
    file.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def build():
    output = ROOT / "dist"
    catalog = []
    search = {}
    with staging_directory(ROOT, ".build-") as staging:
        site = staging / "site"
        shutil.copytree(ROOT / "site", site)
        for note in sorted(NOTES.iterdir()):
            if not SLUG.fullmatch(note.name):
                continue
            metadata = json.loads((note / "note.json").read_text(encoding="utf-8"))
            content = note / "content"
            parser = NoteParser.read(content / "index.html")
            catalog.append({"slug": note.name, "title": metadata["title"], "subject": metadata["subject"]})
            search[note.name] = parser.sections
            shutil.copytree(content, site / "notes" / note.name)
        write_json(site / "catalog.json", catalog)
        write_json(site / "search.json", search)
        previous = staging / "previous"
        if output.exists():
            if output.resolve() != output or not output.is_dir():
                raise ValueError("dist должен быть обычной папкой проекта.")
            output.rename(previous)
        try:
            site.rename(output)
        except OSError:
            if previous.exists():
                previous.rename(output)
            raise
    print(f"Сайт собран. Конспектов: {len(catalog)}")


if __name__ == "__main__":
    build()
