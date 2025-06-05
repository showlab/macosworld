from datetime import datetime

def print_message(content, title=None):
    timestamp = datetime.now().strftime(' %Y-%m-%d %H:%M:%S ')
    timestamp = f'\033[7m{timestamp}\033[0m'
    if title:
        print(f'\r{timestamp} [{title}] {content}')
    else:
        print(f'\r{timestamp} {content}')