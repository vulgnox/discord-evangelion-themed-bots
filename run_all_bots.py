#!/usr/bin/env python3
"""
Bot Launcher - Runs all three Evangelion bots as subprocesses with restart logic.

Features:
- Staggered startup to avoid token rate limits
- Automatic restart on crash
- Graceful shutdown with cleanup
- Per-bot logging to separate outputs
"""
from __future__ import annotations

import subprocess
import sys
import signal
import threading
import time
import logging
from typing import Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

# Bots to launch
BOTS = ["shinji", "asuka", "rei"]

# Restart delay after crash (seconds)
RESTART_DELAY = 5.0

# Startup stagger delay (seconds)
STARTUP_STAGGER = 1.0

# Global state
_processes: dict[str, subprocess.Popen] = {}
_running = True
_lock = threading.Lock()

# ── Bot Process Management ─────────────────────────────────────────────────────

def run_bot(bot_name: str) -> None:
    """
    Run a single bot in a loop with restart on crash.
    
    Args:
        bot_name: Name of the bot file (without .py extension)
    """
    global _running
    
    logger.info("[%s] Starting bot process...", bot_name)
    
    while _running:
        try:
            # Start the bot process
            proc = subprocess.Popen(
                [sys.executable, f"{bot_name}.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            with _lock:
                _processes[bot_name] = proc
            
            logger.info("[%s] Bot started with PID %d", bot_name, proc.pid)
            
            # Wait for process to exit
            proc.wait()
            
            # Process exited - check if we should restart
            with _lock:
                _processes.pop(bot_name, None)
            
            if _running:
                exit_code = proc.returncode
                if exit_code != 0:
                    logger.warning(
                        "[%s] Bot exited with code %d. Restarting in %.1fs...",
                        bot_name, exit_code, RESTART_DELAY
                    )
                else:
                    logger.info("[%s] Bot exited cleanly.", bot_name)
                
                time.sleep(RESTART_DELAY)
                
        except FileNotFoundError:
            logger.error("[%s] Bot file not found: %s.py", bot_name, bot_name)
            break
            
        except Exception as e:
            logger.exception("[%s] Unexpected error: %s", bot_name, e)
            if _running:
                time.sleep(RESTART_DELAY)


def shutdown(signum: Optional[int] = None, frame: Optional[object] = None) -> None:
    """
    Graceful shutdown of all bot processes.
    
    Args:
        signum: Signal number (for signal handler)
        frame: Current stack frame (for signal handler)
    """
    global _running
    
    logger.info("Shutdown signal received...")
    _running = False
    
    # Get current processes
    with _lock:
        procs = list(_processes.items())
    
    # Terminate each process
    for name, proc in procs:
        logger.info("[Launcher] Terminating %s (PID %d)...", name, proc.pid)
        try:
            proc.terminate()
            
            # Wait for graceful termination
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("[Launcher] %s did not terminate gracefully, killing...", name)
                proc.kill()
                proc.wait()
                
        except Exception as e:
            logger.error("[Launcher] Failed to stop %s: %s", name, e)
    
    logger.info("All bots stopped.")
    sys.exit(0)


def get_status() -> dict[str, str]:
    """Get status of all bot processes."""
    with _lock:
        return {
            name: "running" if proc.poll() is None else f"exited ({proc.returncode})"
            for name, proc in _processes.items()
        }


# ── Main Entry Point ───────────────────────────────────────────────────────────

def main() -> None:
    """Launch all bots and wait for shutdown signal."""
    # Setup signal handlers
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    logger.info("=" * 50)
    logger.info("Evangelion Bot Launcher")
    logger.info("=" * 50)
    logger.info("Starting bots: %s", ", ".join(BOTS))
    
    # Start each bot in a separate thread
    threads = []
    for i, bot in enumerate(BOTS):
        t = threading.Thread(target=run_bot, args=(bot,), name=f"BotThread-{bot}", daemon=True)
        t.start()
        threads.append(t)
        
        # Stagger startup to avoid token rate limits
        if i < len(BOTS) - 1:
            logger.info("Waiting %.1fs before next bot...", STARTUP_STAGGER)
            time.sleep(STARTUP_STAGGER)
    
    logger.info("-" * 50)
    logger.info("All bots launched.")
    logger.info("Press Ctrl+C to stop.")
    logger.info("-" * 50)
    
    # Monitor threads and log status periodically
    try:
        while _running:
            time.sleep(30)  # Check every 30 seconds
            
            # Log status
            status = get_status()
            running_count = sum(1 for s in status.values() if s == "running")
            logger.debug("Status check: %d/%d bots running", running_count, len(BOTS))
            
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()


if __name__ == "__main__":
    main()