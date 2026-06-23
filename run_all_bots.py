#!/usr/bin/env python3
"""
Launcher script to run all 3 bots concurrently
Each bot runs in its own thread
"""
import subprocess
import sys
import threading
import time

def run_bot(bot_name):
    """Run a single bot and restart it if it crashes"""
    while True:
        try:
            print(f"[{bot_name}] Starting...")
            process = subprocess.Popen([sys.executable, f"{bot_name}.py"])
            process.wait()
            print(f"[{bot_name}] Process exited, restarting in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            print(f"[{bot_name}] Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    print("Starting all 3 Evangelion bots...")
    
    bots = ["shinji", "asuka", "rei"]
    threads = []
    
    for bot in bots:
        thread = threading.Thread(target=run_bot, args=(bot,), daemon=True)
        thread.start()
        threads.append(thread)
        time.sleep(1)  # Stagger startup
    
    print("All bots launched! Press Ctrl+C to stop.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
