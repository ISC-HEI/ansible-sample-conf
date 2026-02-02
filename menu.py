#!/usr/bin/env python3

from simple_term_menu import TerminalMenu
import subprocess
import os
import sys
import glob
import readline
from cluster import get_all_sessions

CLUSTER_SCRIPT = "cluster.py"
BOLD = "\033[1m"
RESET = "\033[0m"

# Helpers
def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def bold(text):
    return f"{BOLD}{text}{RESET}"

def select_session_menu():
    sessions = get_all_sessions()
    if not sessions:
        print("No active sessions.")
        return None

    options = [
        f"{sid}  ->  {path}"
        for sid, path in sessions.items()
    ]

    menu = TerminalMenu(
        options,
        title="Select a session (verbose)"
    )

    index = menu.show()
    if index is None:
        return None

    return options[index].split()[0]

def complete_path(text, state):
    line = readline.get_line_buffer() or ''

    glob_pattern = line + '*'
    matches = glob.glob(glob_pattern)
    matches = [m + '/' if os.path.isdir(m) else m for m in matches]

    results = []

    if '/' in line:
        last_slash = line.rfind('/')
        prefix = line[:last_slash + 1]

        for m in matches:
            if m.startswith(prefix):
                results.append(prefix + m[len(prefix):])
    else:
        results = matches

    results = sorted(results)

    return results[state] if state < len(results) else None

readline.set_completer_delims(" \t\n")
readline.set_completer(complete_path)
readline.parse_and_bind("tab: complete")

# Commands

def start_cluster():
    inventory = input(bold("Path to inventory file or directory: ")).strip()
    if inventory:
        subprocess.run([sys.executable, CLUSTER_SCRIPT, "start", "-i", inventory])

def run_cluster():
    inventory = input(bold("Inventory path (leave empty to reuse session inventory): ")).strip()
    test = input(bold("Playbook path (leave empty to ping hosts): ")).strip()

    sessions = get_all_sessions()

    if not sessions:
        print(bold("No active sessions found."))
        return

    if len(sessions) == 1:
        session = next(iter(sessions))
        print(bold(f"Using session {session}"))
    else:
        session = select_session_menu()
        if not session:
            return

    cmd = [sys.executable, CLUSTER_SCRIPT, "run", "-s", session]

    if inventory:
        cmd.extend(["-i", inventory])
    if test:
        cmd.extend(["-t", test])

    subprocess.run(cmd)

def stop_cluster():
    rmi = input(bold("Remove docker images? (y/N): ")).strip().lower()
    cmd = [sys.executable, CLUSTER_SCRIPT, "stop"]
    if rmi == "y":
        cmd.append("--rmi")
    subprocess.run(cmd)

def show_sessions():
    verbose = input(bold("Verbose output? (y/N): ")).strip().lower()
    cmd = [sys.executable, CLUSTER_SCRIPT, "sessions"]
    if verbose == "y":
        cmd.append("--verbose")
    subprocess.run(cmd)

def main():
    script_options = [
        "Start - Start the virtual cluster",
        "Run - Run playbook or ping hosts",
        "Stop - Stop the virtual cluster",
        "Sessions - Show all the active sessions",
        "Quit"
    ]

    terminal_menu = TerminalMenu(script_options,
                                 title="Virtual Cluster Manager",
                                 menu_highlight_style=("bold",),
                                 menu_cursor_style=("fg_red", "bold")
                                 )
    while True:
        clear_screen()
        choice = terminal_menu.show()

        if choice == 0:
            start_cluster()
        elif choice == 1:
            run_cluster()
        elif choice == 2:
            stop_cluster()
        elif choice == 3:
            show_sessions()
        elif choice == 4:
            break

        input(bold("\nPress Enter to return to menu..."))

if __name__ == "__main__":
    main()
