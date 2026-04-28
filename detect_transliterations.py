#!/usr/bin/env python3
"""
Detect transliterated (not translated) values in _en.trans files.

Russian transliterations have specific patterns that don't occur in natural English:
- Digraphs: zh, kh, shch, tch, ts (at word boundaries)
- Endings: -iya, -enie, -anie, -ovka, -osti, -stvo, -yy, -iy
- Patterns: double-y (yy), specific syllable combos
"""

import os
import re
import sys
from pathlib import Path
from collections import defaultdict

# Patterns that strongly indicate Russian transliteration
# Each pattern has a weight; if total weight >= threshold, it's flagged
TRANSLIT_PATTERNS = [
    # Strong indicators (weight 3) - almost never in English
    (r'shch', 3),           # щ
    (r'(?<![a-z])kh(?=[aeiouy])', 3),  # х before vowel
    (r'(?<![a-z])zh(?=[aeiouy])', 3),  # ж before vowel
    (r'(?<![sc])tsy', 3),   # ци
    (r'yy\b', 3),           # -ый, -ий at end
    (r'yy(?=[A-Z])', 3),    # -ый/-ий before CamelCase boundary
    (r'(?i)ovaniy', 3),     # -ование
    (r'(?i)eniy[ae]', 3),   # -ение/-ения
    (r'(?i)aniy[ae]', 3),   # -ание/-ания

    # Medium indicators (weight 2)
    (r'(?i)(?<![a-z])obr', 2),    # обр (обработка etc)
    (r'(?i)znach', 2),      # знач (значение)
    (r'(?i)polzov', 2),     # пользов
    (r'(?i)nastro', 2),     # настро (настройка)
    (r'(?i)obnovl', 2),     # обновл (обновление)
    (r'(?i)sozda', 2),      # создa (создание)
    (r'(?i)udalen', 2),     # удален
    (r'(?i)izmenen', 2),    # изменен
    (r'(?i)vypoln', 2),     # выполн (выполнение)
    (r'(?i)zagruz', 2),     # загруз
    (r'(?i)soobshch', 2),   # сообщ
    (r'(?i)preduprezh', 2), # предупрежд
    (r'(?i)tablits', 2),    # таблиц
    (r'(?i)spravochn', 2),  # справочн
    (r'(?i)dokument', 2),   # документ (but careful - "document" is English)
    (r'(?i)registr(?!at|y)', 2),  # регистр (not "registration" or "registry")
    (r'(?i)khranilishch', 2),  # хранилищ
    (r'(?i)opisani', 2),    # описани
    (r'(?i)opoveshch', 2),  # оповещ
    (r'(?i)peremenn', 2),   # перемен (переменная)
    (r'(?i)metadann', 2),   # метаданн
    (r'(?i)rasshiren', 2),  # расширен
    (r'(?i)konfigurats', 2),  # конфигурац
    (r'(?i)ssylk[aiu]', 2),  # ссылк
    (r'(?i)svoystvo', 2),   # свойство
    (r'(?i)podpisk', 2),    # подписк
    (r'(?i)rekvizit', 2),   # реквизит
    (r'(?i)vychisly', 2),   # вычисл
    (r'(?i)formirova', 2),  # формиров (формирование)
    (r'(?i)otladk', 2),     # отладк
    (r'(?i)vygruz', 2),     # выгруз
    (r'(?i)dvizhen', 2),    # движен
    (r'(?i)perechislen', 2),  # перечислен
    (r'(?i)otbor', 2),      # отбор
    (r'(?i)planobmen', 2),  # план обмен
    (r'(?i)regulyarn', 2),  # регулярн

    # Weak indicators (weight 1) - sometimes in English but common in transliteration
    (r'(?i)iya\b', 1),      # -ия ending
    (r'(?i)iye\b', 1),      # -ие ending
    (r'(?i)ovk[aiu]', 1),   # -овка
    (r'(?i)osti\b', 1),     # -ости
    (r'(?i)stvo\b', 1),     # -ство
    (r'(?i)(?<![a-z])vne', 1),  # вне (внешний)
    (r'(?i)(?<![a-z])vnu', 1),  # вну (внутренний)
    (r'(?i)tekushch', 1),   # текущ
    (r'(?i)dlya\b', 1),     # для
    (r'(?i)(?<![a-z])est(?![aeiouy])', 1),  # есть
    (r'(?i)novyy', 1),      # новый
    (r'(?i)staryy', 1),     # старый
]

# Words that look like transliteration patterns but are actually English
ENGLISH_WHITELIST = {
    'document', 'documentation', 'register', 'registration', 'registry',
    'active', 'activate', 'activation', 'administrator', 'administration',
    'collection', 'value', 'string', 'number', 'date', 'time', 'array',
    'object', 'type', 'table', 'form', 'list', 'key', 'name', 'code',
    'data', 'file', 'path', 'node', 'tree', 'property', 'attribute',
    'method', 'function', 'module', 'template', 'picture', 'image',
    'action', 'event', 'handler', 'filter', 'sort', 'order', 'group',
    'field', 'column', 'row', 'cell', 'page', 'panel', 'button',
    'menu', 'command', 'toolbar', 'status', 'message', 'error',
    'warning', 'info', 'debug', 'log', 'result', 'response', 'request',
    'session', 'user', 'role', 'right', 'permission', 'access',
    'minimum', 'maximum', 'xml', 'json', 'html', 'http', 'url', 'uri',
    'ok', 'cancel', 'close', 'open', 'save', 'load', 'delete', 'add',
    'edit', 'update', 'create', 'remove', 'insert', 'select', 'find',
    'search', 'replace', 'copy', 'paste', 'cut', 'undo', 'redo',
    'import', 'export', 'settings', 'options', 'preferences', 'config',
    'configuration', 'connection', 'server', 'client', 'database',
    'query', 'report', 'chart', 'schedule', 'task', 'job', 'process',
    'thread', 'transaction', 'commit', 'rollback', 'lock', 'unlock',
    'version', 'revision', 'history', 'change', 'modified', 'created',
    'deleted', 'archive', 'backup', 'restore', 'publish', 'subscribe',
    'notification', 'subscription', 'extension', 'plugin', 'addon',
    'manager', 'service', 'provider', 'factory', 'builder', 'adapter',
    'converter', 'formatter', 'parser', 'validator', 'generator',
    'container', 'wrapper', 'decorator', 'observer', 'listener',
    'callback', 'delegate', 'proxy', 'cache', 'buffer', 'queue',
    'stack', 'map', 'set', 'dictionary', 'pair', 'tuple', 'record',
    'schema', 'model', 'view', 'controller', 'presentation',
    'abstract', 'annotation', 'boolean', 'integer', 'float', 'double',
    'binary', 'text', 'color', 'font', 'style', 'theme', 'layout',
    'border', 'margin', 'padding', 'width', 'height', 'size', 'position',
    'internal', 'external', 'documentation', 'description',
    'destination', 'registration', 'festival', 'estival',
}


def is_transliteration(value: str) -> tuple[bool, int, list[str]]:
    """Check if a value looks like a Russian transliteration.

    Returns (is_translit, score, matched_patterns)
    """
    if not value or len(value) <= 2:
        return False, 0, []

    # Skip values that are clearly English or technical
    lower = value.lower()

    # Skip if it's a known English word
    # Split CamelCase and check parts
    parts = re.findall(r'[A-Z][a-z]+|[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\b)', value)
    if all(p.lower() in ENGLISH_WHITELIST for p in parts if len(p) > 2):
        return False, 0, []

    # Skip values that are just numbers, symbols, or very short
    if re.match(r'^[\d\s\W]+$', value):
        return False, 0, []

    score = 0
    matches = []

    for pattern, weight in TRANSLIT_PATTERNS:
        if re.search(pattern, value):
            score += weight
            matches.append(pattern)

    threshold = 2  # Minimum score to flag as transliteration
    return score >= threshold, score, matches


def scan_trans_files(root_dir: str) -> dict:
    """Scan all _en.trans files and find transliterated values."""
    results = defaultdict(list)
    stats = {
        'total_files': 0,
        'total_entries': 0,
        'translit_entries': 0,
        'by_type': defaultdict(int),
    }

    for dirpath, dirnames, filenames in os.walk(root_dir):
        for fname in filenames:
            if fname.endswith('_en.trans'):
                filepath = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(filepath, root_dir)
                stats['total_files'] += 1

                with open(filepath, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue

                        if '=' not in line:
                            continue

                        key, _, value = line.partition('=')
                        stats['total_entries'] += 1

                        if not value:
                            continue

                        is_translit, score, matches = is_transliteration(value)

                        if is_translit:
                            stats['translit_entries'] += 1

                            # Determine entry type
                            entry_type = 'other'
                            if '.Key=' in line or key.endswith('.Key'):
                                entry_type = 'Key'
                            elif '.Name=' in line or key.endswith('.Name'):
                                entry_type = 'Name'
                            elif '.Description=' in line or key.endswith('.Description'):
                                entry_type = 'Description'
                            elif '.Value.Value=' in line:
                                entry_type = 'Value'
                            elif '.Title=' in line or key.endswith('.Title'):
                                entry_type = 'Title'
                            elif '.Tooltip=' in line or key.endswith('.Tooltip'):
                                entry_type = 'Tooltip'

                            stats['by_type'][entry_type] += 1

                            results[rel_path].append({
                                'key': key,
                                'value': value,
                                'score': score,
                                'type': entry_type,
                            })

    return results, stats


def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(root_dir, 'src')

    print("Scanning for transliterations in _en.trans files...")
    print(f"Root: {src_dir}")
    print()

    results, stats = scan_trans_files(src_dir)

    # Print summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total files scanned: {stats['total_files']}")
    print(f"Total entries: {stats['total_entries']}")
    print(f"Transliterated entries: {stats['translit_entries']}")
    print(f"Percentage: {stats['translit_entries']/max(stats['total_entries'],1)*100:.1f}%")
    print()
    print("By type:")
    for t, count in sorted(stats['by_type'].items(), key=lambda x: -x[1]):
        print(f"  {t}: {count}")
    print()

    # Print top files
    print("=" * 80)
    print("TOP FILES BY TRANSLITERATION COUNT")
    print("=" * 80)
    sorted_files = sorted(results.items(), key=lambda x: -len(x[1]))
    for filepath, entries in sorted_files[:20]:
        print(f"  {len(entries):5d}  {filepath}")
    print()

    # Print sample entries for each type
    print("=" * 80)
    print("SAMPLE TRANSLITERATED ENTRIES BY TYPE")
    print("=" * 80)

    by_type = defaultdict(list)
    for filepath, entries in results.items():
        for entry in entries:
            by_type[entry['type']].append((filepath, entry))

    for entry_type in ['Name', 'Title', 'Tooltip', 'Description', 'Value', 'Key', 'other']:
        if entry_type not in by_type:
            continue
        entries = by_type[entry_type]
        print(f"\n--- {entry_type} (total: {len(entries)}) ---")
        # Show top 15 by score
        sorted_entries = sorted(entries, key=lambda x: -x[1]['score'])
        for filepath, entry in sorted_entries[:15]:
            print(f"  [{entry['score']:2d}] {entry['value']}")
            print(f"       {filepath} :: {entry['key']}")

    # Write full report to file
    report_path = os.path.join(root_dir, 'transliteration_report.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"Transliteration Report\n")
        f.write(f"Total entries: {stats['translit_entries']}\n\n")

        for filepath, entries in sorted_files:
            f.write(f"\n{'='*80}\n{filepath}\n{'='*80}\n")
            for entry in sorted(entries, key=lambda x: -x['score']):
                f.write(f"  [{entry['type']:>12s}] {entry['key']} = {entry['value']}  (score: {entry['score']})\n")

    print(f"\nFull report written to: {report_path}")


if __name__ == '__main__':
    main()
