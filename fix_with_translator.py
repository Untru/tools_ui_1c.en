#!/usr/bin/env python3
"""
Fix transliterations using Google Translate.

Strategy:
1. Find transliterated values in .dict and .trans files
2. Take the Russian key (original)
3. Split CamelCase into words
4. Translate each word via Google Translate
5. Reassemble into English CamelCase

Usage:
  python fix_with_translator.py --analyze                    # Show what would be fixed
  python fix_with_translator.py --fix-dict                   # Fix common-camelcase_en.dict
  python fix_with_translator.py --fix-trans                  # Fix _en.trans files
  python fix_with_translator.py --fix-common                 # Fix common_en.dict
  python fix_with_translator.py --fix-all                    # Fix everything
  python fix_with_translator.py --analyze --no-translate     # Analyze without calling translator
"""

import os
import re
import sys
import json
import time
from pathlib import Path
from collections import defaultdict

# ── Translation cache ─────────────────────────────────────────────────────

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'translation_cache.json')


def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_cache(cache: dict):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2, sort_keys=True)


# ── Transliteration detection ──────────────────────────────────────────────

STRONG = [
    r'shch', r'(?<![a-z])kh(?=[aeiouy])', r'(?<![a-z])zh(?=[aeiouy])',
    r'yy\b', r'yy(?=[A-Z])', r'(?i)ovaniy', r'(?i)eniy[ae]', r'(?i)aniy[ae]',
]
MEDIUM = [
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
    r'(?i)obrabot', r'(?i)spiso[ck]', r'(?i)strok[aiu]',
    r'(?i)gruppirov', r'(?i)parametr(?!s\b|ic)',
    r'(?i)funkts', r'(?i)protsed', r'(?i)pereme',
    r'(?i)konstant', r'(?i)spravk',
    r'(?i)soedineniy', r'(?i)podklyuch',
    r'(?i)avtoregistrats', r'(?i)avtoobnov',
    r'(?i)vyrazhen', r'(?i)neopredeleno',
]
WEAK = [
    r'(?i)iya\b', r'(?i)iye\b', r'(?i)ovk[aiu]', r'(?i)osti\b', r'(?i)stvo\b',
    r'(?i)tekushch', r'(?i)dlya\b', r'(?i)novyy', r'(?i)staryy',
]


def translit_score(val: str) -> int:
    if not val or len(val) <= 2:
        return 0
    s = 0
    for p in STRONG:
        if re.search(p, val): s += 3
    for p in MEDIUM:
        if re.search(p, val): s += 2
    for p in WEAK:
        if re.search(p, val): s += 1
    return s


def is_transliteration(val: str) -> bool:
    return translit_score(val) >= 2


# ── CamelCase operations ─────────────────────────────────────────────────

def split_camelcase_ru(text: str) -> list[str]:
    """Split Russian CamelCase: 'ТаблицаЗначений' -> ['Таблица', 'Значений']"""
    if not text:
        return []
    return re.findall(r'[А-ЯЁ][а-яё]*|[A-Z][a-z]*|[a-z]+|[а-яё]+|\d+|[_]+', text)


def to_camelcase(words: list[str]) -> str:
    """Join words into CamelCase: ['value', 'table'] -> 'ValueTable'"""
    return ''.join(w.capitalize() if w.isalpha() else w for w in words)


# ── Google Translate integration ──────────────────────────────────────────

_translator = None
_batch_buffer = []
_translate_count = 0


def get_translator():
    global _translator
    if _translator is None:
        from deep_translator import GoogleTranslator
        _translator = GoogleTranslator(source='ru', target='en')
    return _translator


def translate_text(text: str, cache: dict) -> str:
    """Translate Russian text to English, using cache."""
    if text in cache:
        return cache[text]

    global _translate_count
    try:
        result = get_translator().translate(text)
        _translate_count += 1
        if _translate_count % 100 == 0:
            print(f"  [translated {_translate_count} texts...]", file=sys.stderr)
            time.sleep(0.5)  # Rate limiting
        cache[text] = result
        return result
    except Exception as e:
        print(f"  [translate error for '{text}': {e}]", file=sys.stderr)
        return None


def translate_camelcase(ru_text: str, cache: dict) -> str | None:
    """Translate Russian CamelCase to English CamelCase.

    Strategy: translate the whole phrase, then CamelCase-ify the result.
    """
    # Split into words
    words = split_camelcase_ru(ru_text)
    if not words:
        return None

    # Separate Russian words from Latin/numeric parts
    ru_parts = []
    structure = []  # list of (type, value) - 'ru' for russian, 'en' for latin/numeric

    for word in words:
        if re.match(r'^[а-яА-ЯёЁ]+$', word):
            ru_parts.append(word)
            structure.append(('ru', len(ru_parts) - 1))
        else:
            structure.append(('en', word))

    if not ru_parts:
        return None  # Nothing to translate

    # Translate the Russian phrase as a whole (better context)
    ru_phrase = ' '.join(ru_parts)
    translation = translate_text(ru_phrase, cache)
    if not translation:
        return None

    # Split translated phrase into words
    en_words = translation.split()

    # Remove articles and common noise
    en_words = [w for w in en_words if w.lower() not in ('the', 'a', 'an', 'of', 'for', 'to', 'in', 'on', 'at', 'by', 'with', 'is', 'are', 'was', 'were')]

    # Rebuild with structure
    result_parts = []
    en_idx = 0
    for typ, val in structure:
        if typ == 'en':
            result_parts.append(val)
        else:
            # Try to use corresponding translated word
            if en_idx < len(en_words):
                result_parts.append(en_words[en_idx].capitalize())
                en_idx += 1
            # If we have more Russian words than English words, append remaining
    # Append any remaining English words
    while en_idx < len(en_words):
        result_parts.append(en_words[en_idx].capitalize())
        en_idx += 1

    return ''.join(result_parts)


def translate_camelcase_wordbyword(ru_text: str, cache: dict) -> str | None:
    """Alternative: translate each CamelCase word individually."""
    words = split_camelcase_ru(ru_text)
    if not words:
        return None

    result = []
    for word in words:
        if re.match(r'^[а-яА-ЯёЁ]+$', word):
            # Translate single word
            en = translate_text(word, cache)
            if en:
                # Clean up translation - take first word, capitalize
                en_clean = en.split()[0].strip('.,;:!?')
                result.append(en_clean.capitalize())
            else:
                return None
        else:
            result.append(word)

    return ''.join(result)


# ── File processors ──────────────────────────────────────────────────────

def process_camelcase_dict(src_dir: str, cache: dict, fix: bool = False, no_translate: bool = False):
    """Process common-camelcase_en.dict."""
    dict_path = os.path.join(src_dir, 'common-camelcase_en.dict')
    stats = {'total': 0, 'translit': 0, 'fixed': 0, 'unfixable': 0}

    with open(dict_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    fixes = []

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

        if not is_transliteration(val):
            new_lines.append(line)
            continue

        stats['translit'] += 1

        if no_translate:
            new_lines.append(line)
            continue

        # Translate the Russian key (Cyrillic CamelCase)
        translated = translate_camelcase_wordbyword(key, cache)

        if translated and translated != val and not is_transliteration(translated):
            stats['fixed'] += 1
            fixes.append((key, val, translated))
            if fix:
                new_lines.append(f'{key}={translated}\n')
            else:
                new_lines.append(line)
        else:
            stats['unfixable'] += 1
            new_lines.append(line)

    if fix:
        with open(dict_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

    return stats, fixes


def process_trans_files(src_dir: str, cache: dict, fix: bool = False, no_translate: bool = False):
    """Process _en.trans files."""
    stats = {'total_files': 0, 'total_entries': 0, 'translit': 0, 'fixed': 0, 'unfixable': 0}
    fixes = []

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

                if no_translate:
                    new_lines.append(line)
                    continue

                # Extract Russian name from the key path
                parts = trans_key.split('.')
                ru_name = None
                for p in parts:
                    if re.search(r'[а-яА-ЯёЁ]', p):
                        ru_name = p
                        break

                translated = None
                if ru_name:
                    translated = translate_camelcase_wordbyword(ru_name, cache)

                if translated and translated != val and not is_transliteration(translated):
                    stats['fixed'] += 1
                    fixes.append((rel_path, trans_key, val, translated))
                    if fix:
                        new_lines.append(f'{trans_key}={translated}\n')
                        file_changed = True
                    else:
                        new_lines.append(line)
                else:
                    stats['unfixable'] += 1
                    new_lines.append(line)

            if fix and file_changed:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)

    return stats, fixes


def process_common_dict(src_dir: str, cache: dict, fix: bool = False, no_translate: bool = False):
    """Process common_en.dict (non-CamelCase, free-form text values)."""
    dict_path = os.path.join(src_dir, 'common_en.dict')
    stats = {'total': 0, 'translit': 0, 'fixed': 0, 'unfixable': 0}
    fixes = []

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

        if not is_transliteration(val):
            new_lines.append(line)
            continue

        stats['translit'] += 1

        if no_translate:
            new_lines.append(line)
            continue

        # The key has escaped spaces (\ ) - unescape for translation
        ru_text = key.replace('\\ ', ' ').replace('\\=', '=').replace('\\.', '.')
        translated = translate_text(ru_text, cache)

        if translated and not is_transliteration(translated):
            # Re-escape for dict format? No, values don't need escaping
            stats['fixed'] += 1
            fixes.append((key, val, translated))
            if fix:
                new_lines.append(f'{key}={translated}\n')
            else:
                new_lines.append(line)
        else:
            stats['unfixable'] += 1
            new_lines.append(line)

    if fix:
        with open(dict_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

    return stats, fixes


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(root_dir, 'src')

    args = set(sys.argv[1:])
    if not args:
        args = {'--analyze'}

    do_analyze = '--analyze' in args
    do_fix_dict = '--fix-dict' in args or '--fix-all' in args
    do_fix_trans = '--fix-trans' in args or '--fix-all' in args
    do_fix_common = '--fix-common' in args or '--fix-all' in args
    no_translate = '--no-translate' in args

    cache = load_cache()
    print(f"Translation cache: {len(cache)} entries")

    try:
        # 1. Common dict
        if do_fix_common or do_analyze:
            print("\n" + "=" * 80)
            print("COMMON_EN.DICT")
            print("=" * 80)
            stats, fixes = process_common_dict(src_dir, cache, fix=do_fix_common, no_translate=no_translate)
            print(f"Total: {stats['total']}, Translit: {stats['translit']}, Fixed: {stats['fixed']}, Unfixable: {stats['unfixable']}")
            if fixes and do_analyze:
                for key, old, new in fixes[:20]:
                    print(f"  {key}: {old} -> {new}")

        # 2. CamelCase dict
        print("\n" + "=" * 80)
        print("COMMON-CAMELCASE_EN.DICT")
        print("=" * 80)
        stats, fixes = process_camelcase_dict(src_dir, cache, fix=do_fix_dict, no_translate=no_translate)
        print(f"Total: {stats['total']}, Translit: {stats['translit']}, Fixed: {stats['fixed']}, Unfixable: {stats['unfixable']}")
        if fixes and do_analyze:
            print(f"\nSample fixes ({min(30, len(fixes))} of {len(fixes)}):")
            for key, old, new in fixes[:30]:
                print(f"  {key}: {old} -> {new}")

        # 3. Trans files
        print("\n" + "=" * 80)
        print("_EN.TRANS FILES")
        print("=" * 80)
        stats, fixes = process_trans_files(src_dir, cache, fix=do_fix_trans, no_translate=no_translate)
        print(f"Files: {stats['total_files']}, Entries: {stats['total_entries']}, Translit: {stats['translit']}, Fixed: {stats['fixed']}, Unfixable: {stats['unfixable']}")
        if fixes and do_analyze:
            print(f"\nSample fixes ({min(30, len(fixes))} of {len(fixes)}):")
            for filepath, key, old, new in fixes[:30]:
                print(f"  {key}: {old} -> {new}")

    finally:
        save_cache(cache)
        print(f"\nTranslation cache saved: {len(cache)} entries")
        print(f"Total API calls this run: {_translate_count}")


if __name__ == '__main__':
    main()
