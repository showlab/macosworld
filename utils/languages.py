import re

def parse_language_string(s):
    """
    Parses a string of format 'task_<two letters>_env_<two letters>'
    and returns a tuple (task_lang, env_lang) if successful.
    Raises ValueError if the format is incorrect.
    """
    match = re.fullmatch(r'task_([a-z]{2})_env_([a-z]{2})', s)
    if not match:
        raise ValueError(f"Invalid format: {s}")
    return match.group(1), match.group(2)

def parse_language_list(strings):
    """
    Accepts a list of strings, parses each using parse_language_string,
    and returns a list of (task_lang, env_lang) tuples if all are valid.
    """
    return [parse_language_string(s) for s in strings]