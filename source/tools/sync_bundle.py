#!/usr/bin/env python3
"""Synchronise the reviewed source into the adjacent DevSeva.app bundle.

Run the test suite before using --apply.  The developer key, database and
release archives are intentionally never touched by this tool.
"""
from __future__ import annotations

import argparse
import filecmp
import shutil
from pathlib import Path


FILES = (
    'app.py', 'core.py', 'developer.py', 'eventday.py', 'icons.py',
    'importer.py', 'kannada.py', 'mobile.html', 'mobile.py', 'qr.py',
    'qrcodegen.py', 'security.py', 'widgets.py', 'NOTICE.txt', 'README.md',
)
DIRECTORIES = ('samples', 'assets')


def changed(source: Path, bundle: Path) -> list[str]:
    differences = [name for name in FILES
                   if not (bundle / name).exists() or not filecmp.cmp(source / name, bundle / name, shallow=False)]
    for directory in DIRECTORIES:
        for item in (source / directory).rglob('*'):
            if item.is_file():
                relative = item.relative_to(source)
                target = bundle / relative
                if not target.exists() or not filecmp.cmp(item, target, shallow=False):
                    differences.append(str(relative))
    return differences


def sync(source: Path, bundle: Path, differences: list[str]) -> None:
    for name in FILES:
        shutil.copy2(source / name, bundle / name)
    for directory in DIRECTORIES:
        for item in (source / directory).rglob('*'):
            if item.is_file():
                target = bundle / item.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
    print(f'Synchronised {len(differences)} changed file(s) into {bundle.parent.name}.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='copy source files into DevSeva.app')
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    bundle = source.parent / 'DevSeva.app' / 'Contents' / 'Resources'
    if not bundle.is_dir():
        parser.error(f'Cannot find the DevSeva app bundle at {bundle}')
    differences = changed(source, bundle)
    if not differences:
        print('DevSeva.app is already in sync with the source repository.')
        return 0
    print('Changed source files: ' + ', '.join(differences))
    if not args.apply:
        print('Review and test the source, then run: python3 tools/sync_bundle.py --apply')
        return 1
    sync(source, bundle, differences)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
