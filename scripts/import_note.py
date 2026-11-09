"""Import a trusted, UTF-8 study note into the library."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import zipfile

from build import NOTES, NoteParser, SLUG, staging_directory

MAX_BYTES = 64 * 1024 * 1024
MAX_FILES = 256
ASSETS = {".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".gif",
          ".svg", ".avif", ".ico", ".woff", ".woff2"}
SAFE_PART = re.compile(r"[\w.-]+")
RESERVED = {"con", "prn", "aux", "nul", *(p + i for p in ("com", "lpt") for i in "0123456789¹²³")}


def unpack(source, content):
    if source.stat().st_size > MAX_BYTES:
        raise ValueError("Файл превышает 64 МиБ.")
    if source.suffix.lower() == ".html":
        shutil.copyfile(source, content / "index.html")
        return
    if source.suffix.lower() != ".zip":
        raise ValueError("Выберите HTML или ZIP.")
    with zipfile.ZipFile(source) as archive:
        members = archive.infolist()
        if len(members) > MAX_FILES or sum(item.file_size for item in members) > MAX_BYTES:
            raise ValueError("В ZIP больше 256 записей или 64 МиБ после распаковки.")
        files = set()
        seen = set()
        for item in members:
            name = item.orig_filename.removesuffix("/")
            parts = name.split("/")
            if any(not SAFE_PART.fullmatch(part) or part.startswith(".") or part.endswith(".")
                   or part.split(".")[0].lower() in RESERVED for part in parts):
                raise ValueError(f"Недопустимый путь в ZIP: {name!r}")
            kind = stat.S_IFMT(item.external_attr >> 16)
            if kind not in (0, stat.S_IFDIR if item.is_dir() else stat.S_IFREG):
                raise ValueError(f"Недопустимый тип записи: {name!r}")
            key = name.casefold()
            if key in seen:
                raise ValueError(f"Повторяющийся путь: {name!r}")
            seen.add(key)
            if not item.is_dir():
                if name != "index.html" and PurePosixPath(name).suffix.lower() not in ASSETS:
                    raise ValueError(f"Недопустимый файл в ZIP: {name!r}")
                files.add(key)
        if not any(item.filename == "index.html" for item in members):
            raise ValueError("В корне ZIP нужен index.html.")
        for item in members:
            path = PurePosixPath(item.filename)
            if any(parent.as_posix().casefold() in files for parent in path.parents):
                raise ValueError(f"Файл используется как папка: {item.filename!r}")
        for item in members:
            if item.is_dir():
                continue
            destination = content / item.filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as stream, destination.open("xb") as output:
                shutil.copyfileobj(stream, output)


def fingerprint(content):
    digest = hashlib.sha256()
    for file in sorted(content.rglob("*")):
        if file.is_file():
            digest.update(file.relative_to(content).as_posix().encode("utf-8"))
            digest.update(b"\0")
            with file.open("rb") as stream:
                digest.update(hashlib.file_digest(stream, "sha256").digest())
    return digest.hexdigest()


def import_note(source, subject, slug):
    if not SLUG.fullmatch(slug) or slug in RESERVED:
        raise ValueError("Идентификатор должен содержать строчные латинские буквы, цифры и дефисы.")
    subject = " ".join(subject.split())
    if not subject:
        raise ValueError("Укажите предмет.")
    NOTES.mkdir(exist_ok=True)
    with staging_directory(NOTES, ".import-") as temporary:
        staged = temporary / "note"
        content = staged / "content"
        content.mkdir(parents=True)
        unpack(source, content)
        parser = NoteParser.read(content / "index.html")
        if not parser.title or not parser.sections:
            raise ValueError("HTML должен содержать заголовок <title> и текст конспекта.")
        checksum = fingerprint(content)
        for existing in sorted(NOTES.iterdir()):
            if not SLUG.fullmatch(existing.name):
                continue
            metadata = json.loads((existing / "note.json").read_text(encoding="utf-8"))
            if existing.name == slug and metadata["sha256"] != checksum:
                raise ValueError(f"Идентификатор {slug} уже занят другим конспектом.")
            if metadata["sha256"] == checksum:
                return f"Уже в каталоге: {existing.name}"
        metadata = {"title": parser.title, "subject": subject, "sha256": checksum}
        (staged / "note.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        staged.rename(NOTES / slug)
    return f"Добавлен: {slug}"


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source", type=Path)
    cli.add_argument("--subject", required=True)
    cli.add_argument("--slug", required=True)
    args = cli.parse_args()
    try:
        print(import_note(args.source, args.subject, args.slug))
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as error:
        cli.exit(1, f"Импорт не выполнен. {error}\n")
