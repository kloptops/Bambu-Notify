#!/usr/bin/env python3

import argparse
import json
import sys

from pathlib import Path

# NEW: Import the shared definitions
from bambu_defs import STAGE_DESCRIPTIONS

# The keys that should be translated using STAGE_DESCRIPTIONS
STAGE_KEYS = {"stg_cur", "mc_print_sub_stage"}

def format_value(key: str, value):
    """Formats a value for display, translating stage codes if applicable."""
    if key in STAGE_KEYS:
        # Get the string description, or fall back to "Unknown" if code is not found
        description = STAGE_DESCRIPTIONS.get(value, f"Unknown Code ({value})")
        return f"{value} ({description})"
    return value


def compare_entries(old: dict, new: dict, ignore_keys: set, tolerances: dict) -> dict:
    """
    Compares two dictionary entries and returns a dictionary of the differences,
    respecting numerical tolerances.
    """
    # This function remains unchanged...
    changes = {}
    all_keys = set(old.keys()) | set(new.keys())

    for key in all_keys:
        if key in ignore_keys:
            continue

        old_val = old.get(key, "<- Not Present")
        new_val = new.get(key, "<- Not Present")

        if old_val == new_val:
            continue

        if key in tolerances and isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
            if abs(new_val - old_val) < tolerances[key]:
                continue
        
        changes[key] = {'old': old_val, 'new': new_val}
            
    return changes


def display_changes(changes: dict):
    """Prints a formatted list of changes, using the value formatter."""
    for key, values in sorted(changes.items()):
        old_formatted = format_value(key, values['old'])
        new_formatted = format_value(key, values['new'])
        print(f"  - {key}: {old_formatted} -> {new_formatted}")


def run_diff_mode(entries: list, ignore_keys: set, tolerances: dict):
    """
    Analyzes log entries and prints a running diff of all changes.
    """
    print(f"[*] Analyzing in Diff Mode...")
    print(f"[*] Ignoring keys: {', '.join(sorted(list(ignore_keys)))}")
    if tolerances:
        print(f"[*] Applying tolerances: {tolerances}\n")
    else:
        print("")

    previous_entry = None
    for i, current_entry in enumerate(entries):
        if i == 0:
            print(f"--- Entry 1 (Baseline) ---")
            for key, value in sorted(current_entry.items()):
                if key not in ignore_keys:
                    print(f"  - {key}: {format_value(key, value)}") # Use formatter
            previous_entry = current_entry
            continue

        changes = compare_entries(previous_entry, current_entry, ignore_keys, tolerances)

        if changes:
            print(f"\n--- Changes in Entry {i+1} ---")
            display_changes(changes) # Use display helper

        previous_entry = current_entry


def run_watch_mode(entries: list, watch_keys: set, context: int, ignore_keys: set, tolerances: dict):
    """
    Watches for changes in specific keys and prints the surrounding context.
    """
    print(f"[*] Analyzing in Watch Mode...")
    print(f"[*] Watching keys: {', '.join(sorted(list(watch_keys)))}")
    print(f"[*] Context window: {context} entries before and after\n")

    for i in range(1, len(entries)):
        previous_entry = entries[i-1]
        current_entry = entries[i]
        
        triggered_key = None
        for key in watch_keys:
            if previous_entry.get(key) != current_entry.get(key):
                triggered_key = key
                break # Found a trigger

        if triggered_key:
            old_val = previous_entry.get(triggered_key, "N/A")
            new_val = current_entry.get(triggered_key, "N/A")
            print(f"--- Trigger on '{triggered_key}' at Entry {i+1} ({format_value(triggered_key, old_val)} -> {format_value(triggered_key, new_val)}) ---")

            start_index = max(0, i - context)
            end_index = min(len(entries), i + context + 1)
            
            for j in range(start_index, end_index):
                marker = " (TRG)" if j == i else ""
                print(f"\n[Context Entry {j+1}{marker}]")
                
                if j == 0:
                    for key, value in sorted(entries[j].items()):
                        if key not in ignore_keys:
                            print(f"  - {key}: {format_value(key, value)}") # Use formatter
                else:
                    context_changes = compare_entries(entries[j-1], entries[j], ignore_keys, tolerances)
                    if context_changes:
                        display_changes(context_changes) # Use display helper
                    else:
                        print("  (No change from previous entry)")
            
            print("-" * (30 + len(triggered_key)))
            print("\n")


def main():
    parser = argparse.ArgumentParser(
        description="Analyzes Bambu Notify print logs.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    # --- General Arguments ---
    parser.add_argument("logfile", type=Path, help="Path to the print log file.")
    parser.add_argument("--ignore", action="append", default=[], help="Key to ignore in diffs. Can be specified multiple times.")
    parser.add_argument("--tolerance", action="append", default=[], metavar="KEY:VALUE", help="Key and numeric tolerance for ignoring small changes in diffs.")

    # --- Mode-Specific Arguments ---
    watch_group = parser.add_argument_group('Watch Mode', 'Options for watching specific key changes')
    watch_group.add_argument("--watch", action="append", metavar="KEY", help="Activate Watch Mode. Specify a key to watch for changes.")
    watch_group.add_argument("--context", type=int, default=2, help="Number of log entries to show before and after a watched event (default: 2).")

    args = parser.parse_args()

    # --- Input Validation and Setup ---
    if not args.logfile.exists():
        print(f"Error: Log file not found at '{args.logfile}'", file=sys.stderr)
        sys.exit(1)
        
    ignored_keys = {"sequence_id"}
    ignored_keys.update(args.ignore)

    tolerances = {}
    try:
        for item in args.tolerance:
            key, value_str = item.split(':', 1)
            tolerances[key] = float(value_str)
    except ValueError as e:
        print(f"Error parsing --tolerance argument: {e}", file=sys.stderr)
        sys.exit(1)

    # --- Load Log File ---
    try:
        with open(args.logfile, 'r') as f:
            entries = [json.loads(line) for line in f if line.strip()]
    except Exception as e:
        print(f"Error reading or parsing log file: {e}", file=sys.stderr)
        sys.exit(1)

    if not entries:
        print("Log file is empty.")
        return

    # --- Run selected mode ---
    if args.watch:
        watched_keys = set(args.watch)
        run_watch_mode(entries, watched_keys, args.context, ignored_keys, tolerances)
    else:
        run_diff_mode(entries, ignored_keys, tolerances)


if __name__ == '__main__':
    main()
