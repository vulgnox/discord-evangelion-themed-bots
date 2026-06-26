#!/usr/bin/env python3
"""
Launcher — runs all three bots as subprocesses.
Restarts individual bots on crash, cleans up on SIGINT/SIGTERM.
"""
import os
import signal
import subprocess
import sys
import threading
import time

# Ensure the SQLite data directory exists (Fly.io volume or local)
_sqlite_path = os.getenv("SQLITE_PATH", "eva_bots.db")
_data_dir = os.path.dirname(_sqlite_path)
if _data_dir and not os.path.exists(_data_dir):
    try:
        os.makedirs(_data_dir, exist_ok=True)
    except OSError:
        pass

_processes: dict[str, subprocess.Popen] = {}
_running = True
_lock = threading.Lock()


def run_bot(bot_name: str) -> None:
    global _running
    while _running:
        try:
            print(f"[{bot_name}] Starting...")
            proc = subprocess.Popen([sys.executable, f"{bot_name}.py"])
            with _lock:
                _processes[bot_name] = proc
            proc.wait()
            with _lock:
                _processes.pop(bot_name, None)
            if _running:
                code = proc.returncode
                print(f"[{bot_name}] Exited (code {code}). Restarting in 5s...")
                time.sleep(5)
        except Exception as e:
            print(f"[{bot_name}] Error: {e}")
            if _running:
                time.sleep(5)


def shutdown(signum=None, frame=None) -> None:
    global _running
    print("\n[Launcher] Shutting down all bots...")
    _running = False
    with _lock:
        procs = list(_processes.items())
    for name, proc in procs:
        try:
            print(f"[Launcher] Terminating {name}...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception as e:
            print(f"[Launcher] Failed to stop {name}: {e}")
    print("[Launcher] All bots stopped.")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("Starting Evangelion bots...")
    bots = ["shinji", "asuka", "rei"]

    for bot in bots:
        t = threading.Thread(target=run_bot, args=(bot,), daemon=True)
        t.start()
        time.sleep(1.5)  # Stagger to avoid race on DB init

    print("All bots launched. Ctrl+C to stop.")

    try:
        while _running:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()