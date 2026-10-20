"""Supervise Render's web server and inbox worker together; restart on child failure."""
import os
import signal
import subprocess
import sys
import threading


def main():
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    commands = [
        [sys.executable, "-m", "gunicorn", "config.wsgi:application", "--bind", f"0.0.0.0:{os.environ.get('PORT', '10000')}", "--workers", "2", "--timeout", "60", "--access-logfile", "-", "--access-logformat", '%(h)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s'],
        [sys.executable, "manage.py", "run_whatsapp_worker"],
    ]
    children = []
    exit_code = 0
    try:
        for command in commands:
            children.append(subprocess.Popen(command, start_new_session=True))
        while not stop.wait(1):
            if any(child.poll() is not None for child in children):
                exit_code = 1
                break
    finally:
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        for child in children:
            try:
                child.wait(timeout=35)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
