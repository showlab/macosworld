import signal

class TimeoutException(Exception):
    pass

class timeout:
    def __init__(self, seconds, message="Time limit exceeded."):
        self.seconds = seconds
        self.message = message

    def handle_timeout(self, signum, frame):
        raise TimeoutException(self.message)

    def __enter__(self):
        signal.signal(signal.SIGALRM, self.handle_timeout)
        signal.alarm(self.seconds)

    def __exit__(self, exc_type, exc_value, traceback):
        signal.alarm(0)
        