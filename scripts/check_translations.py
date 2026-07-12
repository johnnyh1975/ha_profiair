#!/usr/bin/env python3
"""Translation completeness check — strings.json vs. every translations/*.json.

Compares the flattened key set of strings.json (the authoritative schema
source) against each shipped translation file. Reports:
  - keys present in a translation but missing from strings.json (schema
    drift — e.g. an entity shipped with a translated name that was never
    added to strings.json)
  - keys present in strings.json but missing from a translation (an
    incomplete translation)

This project ships de + en. Both are currently fully in sync with
strings.json (329 keys each), so this check starts green and stays that
way only if new entities are added to all three files together — which is
exactly the drift it exists to catch.

ALLOWED_STRINGS_ONLY is deliberately empty: there is currently no known,
verified-harmless asymmetry to exempt. Add to it only for a case that has
actually been checked and understood, with a comment explaining why —
never just to silence a failure.

Exit code 0 = all translations complete. Exit code 1 = at least one gap.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "kwl_fraenkische"
STRINGS_PATH = BASE_DIR / "strings.json"
TRANSLATIONS_DIR = BASE_DIR / "translations"

# Keys allowed to exist in strings.json but be absent from a shipped
# translation file. Empty on purpose — see module docstring.
ALLOWED_STRINGS_ONLY: set[str] = set()


def flatten_keys(d: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(d, dict):
        for k, v in d.items():
            path = f"{prefix}.{k}" if prefix else k
            keys.add(path)
            keys |= flatten_keys(v, path)
    return keys


def main() -> int:
    if not STRINGS_PATH.exists():
        print(f"::error::{STRINGS_PATH} not found")
        return 1

    with open(STRINGS_PATH, encoding="utf-8") as f:
        strings_keys = flatten_keys(json.load(f))

    translation_files = sorted(TRANSLATIONS_DIR.glob("*.json"))
    if not translation_files:
        print(f"::error::No translation files found in {TRANSLATIONS_DIR}")
        return 1

    had_problems = False

    for path in translation_files:
        lang = path.stem
        with open(path, encoding="utf-8") as f:
            lang_keys = flatten_keys(json.load(f))

        missing_in_lang = sorted(strings_keys - lang_keys - ALLOWED_STRINGS_ONLY)
        extra_in_lang = sorted(lang_keys - strings_keys)

        if missing_in_lang:
            had_problems = True
            print(
                f"::error::translations/{lang}.json is missing "
                f"{len(missing_in_lang)} key(s) present in strings.json:"
            )
            for k in missing_in_lang:
                print(f"    {k}")

        if extra_in_lang:
            had_problems = True
            print(
                f"::error::translations/{lang}.json has {len(extra_in_lang)} "
                f"key(s) not in strings.json (strings.json is stale — add them there too):"
            )
            for k in extra_in_lang:
                print(f"    {k}")

        if not missing_in_lang and not extra_in_lang:
            print(f"OK: translations/{lang}.json matches strings.json ({len(lang_keys)} keys)")

    return 1 if had_problems else 0


if __name__ == "__main__":
    sys.exit(main())
