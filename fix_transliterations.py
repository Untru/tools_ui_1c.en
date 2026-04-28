#!/usr/bin/env python3
"""
Fix transliterated values in common-camelcase_en.dict and _en.trans files.

Strategy:
1. For each transliterated value, find the original Russian key
2. Split Russian key into CamelCase words
3. Translate each word using the ru_en_words dictionary
4. Reassemble into English CamelCase

Usage:
  python fix_transliterations.py --analyze          # Show what would be fixed
  python fix_transliterations.py --fix-dict         # Fix common-camelcase_en.dict
  python fix_transliterations.py --fix-trans        # Fix _en.trans files
  python fix_transliterations.py --fix-all          # Fix everything
"""

import os
import re
import sys
from pathlib import Path
from collections import defaultdict

# Import word dictionary
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ru_en_words import WORDS


# ── Transliteration detection ──────────────────────────────────────────────

STRONG_PATTERNS = [
    r'shch', r'(?<![a-z])kh(?=[aeiouy])', r'(?<![a-z])zh(?=[aeiouy])',
    r'yy\b', r'yy(?=[A-Z])', r'(?i)ovaniy', r'(?i)eniy[ae]', r'(?i)aniy[ae]',
]
MEDIUM_PATTERNS = [
    r'(?i)znach', r'(?i)polzov', r'(?i)nastro', r'(?i)obnovl',
    r'(?i)sozda', r'(?i)udalen', r'(?i)izmenen', r'(?i)vypoln',
    r'(?i)zagruz', r'(?i)soobshch', r'(?i)tablits', r'(?i)spravochn',
    r'(?i)khranilishch', r'(?i)opisani', r'(?i)opoveshch', r'(?i)peremenn',
    r'(?i)metadann', r'(?i)rasshiren', r'(?i)konfigurats', r'(?i)ssylk[aiu]',
    r'(?i)svoystvo', r'(?i)podpisk', r'(?i)rekvizit', r'(?i)vychisly',
    r'(?i)formirova', r'(?i)otladk', r'(?i)vygruz', r'(?i)dvizhen',
    r'(?i)perechislen', r'(?i)otbor', r'(?i)regulyarn',
    r'(?i)dokument(?!s\b|ation|ed|ing)',
    r'(?i)registr(?!at|y\b|ed|ing)',
]
WEAK_PATTERNS = [
    r'(?i)iya\b', r'(?i)iye\b', r'(?i)ovk[aiu]', r'(?i)osti\b', r'(?i)stvo\b',
    r'(?i)tekushch', r'(?i)dlya\b', r'(?i)novyy', r'(?i)staryy',
]


def translit_score(val: str) -> int:
    if not val or len(val) <= 2:
        return 0
    s = 0
    for p in STRONG_PATTERNS:
        if re.search(p, val): s += 3
    for p in MEDIUM_PATTERNS:
        if re.search(p, val): s += 2
    for p in WEAK_PATTERNS:
        if re.search(p, val): s += 1
    return s


def is_transliteration(val: str) -> bool:
    return translit_score(val) >= 2


# ── CamelCase splitting ───────────────────────────────────────────────────

def split_camelcase_ru(text: str) -> list[str]:
    """Split Russian CamelCase into words.
    'ТаблицаЗначений' -> ['Таблица', 'Значений']
    """
    if not text:
        return []
    # Split on transitions: lowercase->uppercase or end of uppercase run
    parts = re.findall(r'[А-ЯЁ][а-яё]*|[A-Z][a-z]*|[a-zа-яё]+|[A-ZА-ЯЁ]+|\d+', text)
    return parts


def split_camelcase_en(text: str) -> list[str]:
    """Split English CamelCase into words."""
    if not text:
        return []
    parts = re.findall(r'[A-Z][a-z]*|[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\b)|\d+', text)
    return parts


# ── Translation engine ────────────────────────────────────────────────────

def translate_word(ru_word: str) -> str | None:
    """Translate a single Russian word to English using dictionary."""
    # Direct lookup
    if ru_word in WORDS:
        return WORDS[ru_word]

    # Try title case
    titled = ru_word[0].upper() + ru_word[1:] if len(ru_word) > 1 else ru_word.upper()
    if titled in WORDS:
        return WORDS[titled]

    # Try lowercase
    lower = ru_word.lower()
    titled_lower = lower[0].upper() + lower[1:] if len(lower) > 1 else lower.upper()
    if titled_lower in WORDS:
        return WORDS[titled_lower]

    # Try uppercase (for abbreviations)
    upper = ru_word.upper()
    if upper in WORDS:
        return WORDS[upper]

    return None


def translate_camelcase(ru_text: str) -> str | None:
    """Translate Russian CamelCase to English CamelCase.

    Returns None if any word can't be translated.
    """
    words = split_camelcase_ru(ru_text)
    if not words:
        return None

    result = []
    untranslated = []

    for word in words:
        # Skip pure Latin/numeric parts
        if re.match(r'^[A-Za-z0-9_]+$', word):
            result.append(word)
            continue

        en = translate_word(word)
        if en is None:
            untranslated.append(word)
            result.append(f'<{word}>')
        else:
            result.append(en)

    if untranslated:
        return None  # Can't fully translate

    return ''.join(result)


# ── File processing ───────────────────────────────────────────────────────

def process_camelcase_dict(src_dir: str, fix: bool = False) -> dict:
    """Process common-camelcase_en.dict."""
    dict_path = os.path.join(src_dir, 'common-camelcase_en.dict')
    stats = {'total': 0, 'translit': 0, 'fixed': 0, 'unfixable': 0}
    fixes = []
    unfixable = []

    with open(dict_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        stripped = line.rstrip('\n')
        if not stripped or stripped.startswith('#'):
            new_lines.append(line)
            continue

        if '=' not in stripped:
            new_lines.append(line)
            continue

        key, _, val = stripped.partition('=')
        stats['total'] += 1

        if key == val or not is_transliteration(val):
            new_lines.append(line)
            continue

        stats['translit'] += 1

        # The key is the Russian CamelCase, try to translate it
        # But the key in this file is also Russian (Cyrillic), so we use it directly
        translated = translate_camelcase(key)

        if translated and translated != val:
            stats['fixed'] += 1
            fixes.append((key, val, translated))
            if fix:
                new_lines.append(f'{key}={translated}\n')
            else:
                new_lines.append(line)
        else:
            stats['unfixable'] += 1
            # Try partial info
            words = split_camelcase_ru(key)
            partial = []
            for w in words:
                if re.match(r'^[A-Za-z0-9_]+$', w):
                    partial.append(w)
                else:
                    en = translate_word(w)
                    partial.append(en if en else f'?{w}?')
            unfixable.append((key, val, ''.join(partial)))
            new_lines.append(line)

    if fix:
        with open(dict_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

    return stats, fixes, unfixable


def process_trans_files(src_dir: str, fix: bool = False) -> dict:
    """Process all _en.trans files."""
    stats = {'total_files': 0, 'total_entries': 0, 'translit': 0, 'fixed': 0, 'unfixable': 0}
    all_fixes = []
    all_unfixable = []

    for dirpath, dirnames, filenames in os.walk(src_dir):
        for fname in filenames:
            if not fname.endswith('_en.trans'):
                continue

            filepath = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(filepath, src_dir)
            stats['total_files'] += 1

            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            new_lines = []
            file_changed = False

            for line in lines:
                stripped = line.rstrip('\n')
                if not stripped or stripped.startswith('#'):
                    new_lines.append(line)
                    continue

                if '=' not in stripped:
                    new_lines.append(line)
                    continue

                trans_key, _, val = stripped.partition('=')
                stats['total_entries'] += 1

                if not val or not is_transliteration(val):
                    new_lines.append(line)
                    continue

                stats['translit'] += 1

                # For .trans files, the trans_key contains the metadata path
                # e.g. "Attribute.ПериодAutoобновления.Name"
                # We need to extract the Russian name from the key
                # The Russian name is the second part (between first and second dot)
                parts = trans_key.split('.')
                ru_name = None
                if len(parts) >= 2:
                    # Find the part that contains Cyrillic
                    for p in parts:
                        if re.search(r'[а-яА-ЯёЁ]', p):
                            ru_name = p
                            break

                translated = None
                if ru_name:
                    translated = translate_camelcase(ru_name)

                if translated and translated != val:
                    stats['fixed'] += 1
                    all_fixes.append((rel_path, trans_key, val, translated))
                    if fix:
                        new_lines.append(f'{trans_key}={translated}\n')
                        file_changed = True
                    else:
                        new_lines.append(line)
                else:
                    stats['unfixable'] += 1
                    all_unfixable.append((rel_path, trans_key, val))
                    new_lines.append(line)

            if fix and file_changed:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)

    return stats, all_fixes, all_unfixable


def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(root_dir, 'src')

    args = sys.argv[1:]
    if not args:
        args = ['--analyze']

    do_analyze = '--analyze' in args
    do_fix_dict = '--fix-dict' in args or '--fix-all' in args
    do_fix_trans = '--fix-trans' in args or '--fix-all' in args

    print(f"Dictionary has {len(WORDS)} word mappings")
    print()

    # Process camelcase dict
    print("=" * 80)
    print("COMMON-CAMELCASE_EN.DICT")
    print("=" * 80)

    dict_stats, dict_fixes, dict_unfixable = process_camelcase_dict(
        src_dir, fix=do_fix_dict
    )

    print(f"Total entries: {dict_stats['total']}")
    print(f"Transliterated: {dict_stats['translit']}")
    print(f"Can fix: {dict_stats['fixed']}")
    print(f"Cannot fix (missing words): {dict_stats['unfixable']}")

    if do_fix_dict:
        print(f"\n>>> FIXED {dict_stats['fixed']} entries in common-camelcase_en.dict")

    if do_analyze and dict_fixes:
        print(f"\nSample fixes (showing {min(30, len(dict_fixes))} of {len(dict_fixes)}):")
        for key, old_val, new_val in dict_fixes[:30]:
            print(f"  {key}")
            print(f"    OLD: {old_val}")
            print(f"    NEW: {new_val}")

    if do_analyze and dict_unfixable:
        print(f"\nUnfixable (showing {min(20, len(dict_unfixable))} of {len(dict_unfixable)}):")
        for key, old_val, partial in dict_unfixable[:20]:
            print(f"  {key} = {old_val}")
            print(f"    partial: {partial}")

    # Process trans files
    print()
    print("=" * 80)
    print("_EN.TRANS FILES")
    print("=" * 80)

    trans_stats, trans_fixes, trans_unfixable = process_trans_files(
        src_dir, fix=do_fix_trans
    )

    print(f"Total files: {trans_stats['total_files']}")
    print(f"Total entries: {trans_stats['total_entries']}")
    print(f"Transliterated: {trans_stats['translit']}")
    print(f"Can fix: {trans_stats['fixed']}")
    print(f"Cannot fix: {trans_stats['unfixable']}")

    if do_fix_trans:
        print(f"\n>>> FIXED {trans_stats['fixed']} entries in .trans files")

    if do_analyze and trans_fixes:
        print(f"\nSample fixes (showing {min(30, len(trans_fixes))} of {len(trans_fixes)}):")
        for filepath, key, old_val, new_val in trans_fixes[:30]:
            print(f"  {filepath}")
            print(f"    {key}: {old_val} -> {new_val}")

    # Write missing words report
    if dict_unfixable or trans_unfixable:
        missing = defaultdict(int)
        for key, old_val, partial in dict_unfixable:
            words = split_camelcase_ru(key)
            for w in words:
                if not re.match(r'^[A-Za-z0-9_]+$', w) and translate_word(w) is None:
                    missing[w] += 1

        for filepath, key, old_val in trans_unfixable:
            parts = key.split('.')
            for p in parts:
                if re.search(r'[а-яА-ЯёЁ]', p):
                    words = split_camelcase_ru(p)
                    for w in words:
                        if not re.match(r'^[A-Za-z0-9_]+$', w) and translate_word(w) is None:
                            missing[w] += 1

        report_path = os.path.join(root_dir, 'missing_words.txt')
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("# Missing Russian words not in dictionary\n")
            f.write("# Format: count  word\n\n")
            for word, count in sorted(missing.items(), key=lambda x: -x[1]):
                f.write(f"{count:5d}  {word}\n")

        print(f"\nMissing words report: {report_path} ({len(missing)} unique words)")

    # Summary
    total_fixed = dict_stats['fixed'] + trans_stats['fixed']
    total_unfixable = dict_stats['unfixable'] + trans_stats['unfixable']
    total_translit = dict_stats['translit'] + trans_stats['translit']
    print()
    print("=" * 80)
    print(f"TOTAL: {total_translit} transliterated, {total_fixed} fixable ({total_fixed/max(total_translit,1)*100:.0f}%), {total_unfixable} need more words")
    print("=" * 80)


if __name__ == '__main__':
    main()
