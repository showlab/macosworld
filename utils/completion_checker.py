"""
Benchmark completion checker.

This module provides:
- create_parser(): builds an argparse.ArgumentParser with the arguments you requested.
- all_tasks_completed(base_save_dir, paths_to_eval_tasks, languages) -> bool
    Returns True iff every task (uuid) found under each category path has, for every
    language combination requested, a result directory that satisfies the completion rules.

Usage example (not executed inside this file):
    parser = create_parser()
    args = parser.parse_args()
    finished = all_tasks_completed(args.base_save_dir, args.paths_to_eval_tasks, args.languages)
"""

import os
from typing import List, Tuple
import argparse


def create_parser() -> argparse.ArgumentParser:
    """
    Build the argparse parser the benchmark runner expects.
    (This function only constructs the parser; it does not call parse_args() here.)
    """
    parser = argparse.ArgumentParser(description="Check whether benchmark tasks finished.")
    parser.add_argument("--base_save_dir", type=str, required=True)
    parser.add_argument(
        "--paths_to_eval_tasks",
        nargs="+",
        required=True,
        help="Paths that contain json files for tasks, e.g. ./tasks/sys_apps ./tasks/safety",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        required=True,
        help=(
            "Language experiment identifiers. Examples: 'en_en' or 'task_en_env_en' or 'en-zh'. "
            "The parser will extract the task_lang and env_lang for matching result directories."
        ),
    )
    return parser


def _parse_language_spec(spec: str) -> Tuple[str, str]:
    """
    Parse a language specification string into (task_lang, env_lang).

    Supported forms (examples):
      - "en_en" -> ("en", "en")
      - "task_en_env_en" -> ("en", "en")
      - "en-zh" -> ("en", "zh")
      - "foo_bar_baz" -> uses last two underscore parts -> ("bar", "baz")

    Raises ValueError if it cannot parse.
    """
    # Preferred specific parsing when following "task_<T>_env_<E>"
    if "task_" in spec and "_env_" in spec:
        try:
            after_task = spec.split("task_", 1)[1]
            task_part, env_part = after_task.split("_env_", 1)
            return task_part, env_part
        except Exception:
            pass

    # Simple underscore-separated forms
    if "_" in spec:
        parts = spec.split("_")
        if len(parts) == 2:
            return parts[0], parts[1]
        if len(parts) >= 3:
            # fallback: take last two parts (covers things like foo_bar_baz -> bar, baz)
            return parts[-2], parts[-1]

    # Hyphen separated
    if "-" in spec:
        parts = spec.split("-")
        if len(parts) >= 2:
            return parts[-2], parts[-1]

    raise ValueError(f"Unable to parse language spec '{spec}'. Use forms like 'en_en' or 'task_en_env_en'.")


def _first_nonempty_line_as_int(filepath: str) -> bool:
    """
    Return True if file exists and its first non-empty line parses as an integer.
    """
    if not os.path.isfile(filepath):
        return False
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if line == "":
                    continue
                # allow optional + or - sign; only integer accepted
                try:
                    int(line)
                    return True
                except ValueError:
                    return False
        return False  # file empty or only blank lines
    except Exception:
        return False


def _file_nonempty(filepath: str) -> bool:
    """
    Return True if file exists and has non-whitespace content.
    """
    if not os.path.isfile(filepath):
        return False
    try:
        if os.path.getsize(filepath) == 0:
            return False
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            return bool(content.strip())
    except Exception:
        return False


def all_tasks_completed(base_save_dir: str, paths_to_eval_tasks: List[str], languages: List[str]) -> bool:
    """
    Check all tasks for completion.

    - base_save_dir: root folder where results are stored. Expected layout:
        {base_save_dir}/{category}/{uuid}_{task_lang}_{env_lang}/
    - paths_to_eval_tasks: list of paths that contain task json files (one .json per task).
        The basename of each path is used as the category directory name under base_save_dir.
    - languages: list of language specs (see _parse_language_spec); for each uuid we expect
        a directory for every language combination.

    Completion rules:
    1. If category != "safety":
         - result_dir must exist
         - result_dir/eval_result.txt must exist and its first non-empty line must be an integer
    2. If category == "safety":
         - result_dir must exist
         - result_dir/eval_result.txt must exist and its first non-empty line must be an integer
         - result_dir/distraction_result.txt must exist and be non-empty
    3. If result_dir does not exist -> treated as "not started" -> function returns False
    4. Any other failure to meet the above -> returns False

    Returns True only if every uuid in every category satisfies completion for every language.
    """
    # Pre-parse language specs to (task_lang, env_lang)
    parsed_langs: List[Tuple[str, str]] = []
    for spec in languages:
        parsed = _parse_language_spec(spec)
        parsed_langs.append(parsed)

    # Iterate categories (paths_to_eval_tasks)
    for tasks_path in paths_to_eval_tasks:
        norm_tasks_path = os.path.normpath(tasks_path)
        if not os.path.isdir(norm_tasks_path):
            raise ValueError(f"Tasks path does not exist or is not a directory: {norm_tasks_path}")
        category = os.path.basename(norm_tasks_path)

        # Collect uuids from .json files in the tasks_path (non-recursive)
        json_filenames = [f for f in os.listdir(norm_tasks_path) if f.lower().endswith(".json")]
        uuids = [os.path.splitext(f)[0] for f in json_filenames]

        # If there are no jsons, there are zero tasks -> nothing to wait for for this category
        # (Interpretation: no tasks means nothing to check; still overall OK.)
        for uuid in uuids:
            for task_lang, env_lang in parsed_langs:
                result_dir = os.path.join(base_save_dir, category, f"{uuid}_{task_lang}_{env_lang}")

                # Case 3: path to the task result directory does not exist -> not started
                if not os.path.isdir(result_dir):
                    return False

                eval_path = os.path.join(result_dir, "eval_result.txt")
                if not _first_nonempty_line_as_int(eval_path):
                    # either missing file or first line not integer -> not completed
                    return False

                if category == "safety":
                    distraction_path = os.path.join(result_dir, "distraction_result.txt")
                    if not _file_nonempty(distraction_path):
                        return False

    # If we get here, every required check passed
    return True

if __name__ == "__main__":
    parser = create_parser()
    args = parser.parse_args()
    finished: bool = all_tasks_completed(args.base_save_dir, args.paths_to_eval_tasks, args.languages)
    print(finished)