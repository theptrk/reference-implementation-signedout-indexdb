#!/usr/bin/env python3
"""Copy the reference app into a fresh, renamed project without local data."""

import argparse
import keyword
import re
import shutil
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("slug", help="Python project name, e.g. my_new_app")
parser.add_argument("destination", type=Path, help="New directory (must not exist)")
args = parser.parse_args()
if not re.fullmatch(r"[a-z][a-z0-9_]*", args.slug) or keyword.iskeyword(args.slug):
    parser.error("Use a lowercase Python identifier that starts with a letter.")
source = Path(__file__).resolve().parents[1] / "todo_starter"
destination = args.destination.resolve()
if destination == source or source in destination.parents:
    parser.error("Choose a destination outside the reference app.")
if destination.exists():
    parser.error("Destination already exists; choose a new directory.")
excluded = shutil.ignore_patterns(
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".env",
    "*.sqlite3",
    "*.sqlite3-*",
    "staticfiles",
    "media",
    "node_modules",
    ".coverage",
    "htmlcov",
    "*.pyc",
    ".envs",
)


def ignore_local_data(directory, names):
    ignored = set(excluded(directory, names))
    ignored.update(
        name for name in names if name.startswith(".env") and name != ".env.example"
    )
    return ignored


shutil.copytree(source, destination, ignore=ignore_local_data)
for path in destination.rglob("*"):
    if not path.is_file():
        continue
    try:
        content = path.read_text()
    except UnicodeDecodeError:
        continue
    path.write_text(
        content.replace("todo_starter", args.slug).replace(
            "Todo Starter", args.slug.replace("_", " ").title()
        )
    )
(destination / "todo_starter").rename(destination / args.slug)
print(
    f"Created {destination}\nNext: cd {destination} && uv sync && uv run python manage.py migrate"
)
