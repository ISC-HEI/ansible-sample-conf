import yaml
import subprocess
import sys
import os
import argparse
import json
import shutil
import socket

TEMP_DIRECTORY = "./temp"
MEMO_FILE = f"{TEMP_DIRECTORY}/.lab_session.json"

os.makedirs(TEMP_DIRECTORY, exist_ok=True)

# Helpers
def load_inventory(path_or_file):
    """Load inventory from a YAML file or directory of YAML files, merging hosts."""
    data = {}
    if os.path.isdir(path_or_file):
        for filename in os.listdir(path_or_file):
            if filename.endswith((".yaml", ".yml")):
                full_path = os.path.join(path_or_file, filename)
                with open(full_path, "r") as f:
                    file_data = yaml.safe_load(f)
                    if file_data:
                        for key, val in file_data.items():
                            if key not in data:
                                data[key] = val
                            else:
                                for group_name, group_content in val.get("children", {}).items():
                                    if "children" not in data[key]:
                                        data[key]["children"] = {}
                                    if group_name not in data[key]["children"]:
                                        data[key]["children"][group_name] = group_content
                                    else:
                                        existing_hosts = data[key]["children"][group_name].get("hosts", {})
                                        new_hosts = group_content.get("hosts", {})
                                        existing_hosts.update(new_hosts)
                                        data[key]["children"][group_name]["hosts"] = existing_hosts
    else:
        with open(path_or_file, "r") as f:
            data = yaml.safe_load(f)
    return data

def generate_docker_compose(data, sessionId):
    """Generate docker-compose.yml dictionary from inventory data."""
    docker_compose = {"services": {}}
    root = data.get("test_inv", data)
    vars = root.get("vars", {})
    dockerfileVersion = vars.get("dockerfile")
    children = root.get("children", {})

    for group in children.values():
        for host, vars in group.get("hosts", {}).items():
            port = vars.get("ansible_port")
            if not port:
                continue
            host_port = session_port_offset(port, sessionId)



            docker_compose["services"][host] = {
                "build": {
                    "context": "../build",
                    "dockerfile": f"Dockerfile.{dockerfileVersion}",
                },
                "container_name": f"{sessionId}-{host}",
                "command": "/usr/sbin/sshd -D",
                "ports": [f"{host_port}:22"],
                "networks": [f"{sessionId}-lab-net"],
                "deploy": {
                    "resources": {
                        "limits": {"cpus": "1.0", "memory": "512M"}
                    }
                },
            }

    docker_compose["networks"] = {f"{sessionId}-lab-net": {"driver": "bridge"}}
    return docker_compose

def fix_hosts(sessionId):
    """Fix /etc/hosts in all running containers."""
    container_ids = subprocess.check_output(
        [
            "docker", "compose",
            "-p", sessionId.lower(),
            "-f", f"temp/docker-compose-{sessionId}.yml",
            "ps", "-q"
        ]
    ).decode().splitlines()

    for cid in container_ids:
        cname = subprocess.check_output(
            ["docker", "inspect", "-f", "{{.Name}}", cid]
        ).decode().strip().lstrip("/")
        print(f"  -> Fixing /etc/hosts in {cname}")
        subprocess.run(
            [
                "docker", "exec", "-u", "root", cid, "bash", "-c",
                "cp /etc/hosts /etc/hosts.bak && umount /etc/hosts && mv /etc/hosts.bak /etc/hosts",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

def is_port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except:
        return False

# session

def create_session(path):
    sessions = {}

    if os.path.exists(MEMO_FILE):
        with open(MEMO_FILE, "r") as f:
            try:
                sessions = json.load(f)
            except json.JSONDecodeError:
                sessions = []

    if sessions:
        numbers = [int(s[1:]) for s in sessions if s.startswith("S") and s[1:].isdigit()]
        next_number = max(numbers) + 1 if numbers else 1
    else:
        next_number = 1

    new_session = f"S{next_number:02d}"
    sessions[new_session] = path

    with open(MEMO_FILE, "w") as f:
        json.dump(sessions, f)

    return new_session

def update_session(sessionId, path):
    data = {}
    if os.path.exists(MEMO_FILE):
        with open(MEMO_FILE, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}

    data[sessionId] = path
    with open(MEMO_FILE, "w") as f:
        json.dump(data, f)

def get_session(sessionId):
    if os.path.exists(MEMO_FILE):
        with open(MEMO_FILE, "r") as f:
            try:
                data = json.load(f)
                return data.get(sessionId)
            except json.JSONDecodeError:
                return None
    return None

def get_all_sessions():
    if os.path.exists(MEMO_FILE):
        with open(MEMO_FILE, "r") as f:
            try:
                data = json.load(f)
                return data
            except json.JSONDecodeError:
                return None
    return None

def generate_session_inventory(data, sessionId, output_path):
    root_name = "test_inv" if "test_inv" in data else None
    root = data[root_name] if root_name else data

    session_root = {
        "vars": root.get("vars", {}),
        "children": {}
    }

    for group_name, group in root.get("children", {}).items():
        session_root["children"][group_name] = {"hosts": {}}

        for host, vars in group.get("hosts", {}).items():
            port = vars.get("ansible_port")
            if not port:
                continue

            session_root["children"][group_name]["hosts"][host] = {
                **vars,
                "ansible_host": "127.0.0.1",
                "ansible_port": session_port_offset(port, sessionId),
            }

    session_inventory = {root_name: session_root} if root_name else session_root

    with open(output_path, "w") as f:
        yaml.dump(session_inventory, f, sort_keys=False)

def session_port_offset(base_port, sessionId):
    port = base_port + (int(sessionId[1:]) - 1) * 100
    while is_port_open(port):
        port += 10
    return port

# Functions link to command

def start(inventory):
    print(f"Using inventory: {inventory}")
    sessionId = create_session(inventory)
    print(f"Your session id is {sessionId}")

    print("Loading inventory...")
    try:
        data = load_inventory(inventory)
    except Exception as e:
        print(f"Error reading inventory: {e}")
        sys.exit(1)

    print("Generating docker-compose.yml...")
    session_inventory_path = f"temp/inventory-{sessionId}.yml"

    print("Generating session inventory...")
    generate_session_inventory(data, sessionId, session_inventory_path)

    update_session(sessionId, session_inventory_path)

    docker_compose = generate_docker_compose(data, sessionId)


    with open(f"temp/docker-compose-{sessionId}.yml", "w") as f:
        yaml.dump(docker_compose, f, sort_keys=False)

    print("Starting containers...")
    try:
        subprocess.run(
            [
                "docker", "compose",
                "-p", sessionId.lower(),
                "-f", f"temp/docker-compose-{sessionId}.yml",
                "up", "-d", "--build"
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        print("Error starting Docker containers")
        shutil.rmtree("temp")
        sys.exit(1)

    print("Fixing /etc/hosts in containers...")
    fix_hosts(sessionId)

def run(inventory, test_path, sessionId):
    sessions = get_all_sessions()

    if not sessions:
        print("Error: no active session found. Please start a session first.")
        sys.exit(1)

    if sessionId:
        if sessionId not in sessions:
            print(f"Error: session {sessionId} does not exist")
            sys.exit(1)
    else:
        if len(sessions) == 1:
            sessionId = next(iter(sessions))
        else:
            print("Error: multiple sessions found, please specify one with -s")
            sys.exit(1)

    if inventory:
        update_session(sessionId, inventory)
    else:
        inventory = sessions.get(sessionId)
        if not inventory:
            print("Error: no inventory associated with this session")
            sys.exit(1)

    if test_path:
        print(f"Running playbook {test_path} on inventory {inventory} (session {sessionId})...")
        subprocess.run(
            ["ansible-playbook", "-i", inventory, test_path, "-e", "h=all"]
        )
    else:
        print(f"Pinging all hosts in inventory {inventory} (session {sessionId})...")
        subprocess.run(
            ["ansible", "all", "-m", "ping", "-i", inventory]
        )

def stop(rmi):
    sessions = get_all_sessions()
    if (sessions):
        for s in sessions:
            command = [
                "docker", "compose",
                "-p", s.lower(),
                "-f", f"temp/docker-compose-{s}.yml",
                "down"
            ]
            if rmi:
                command.extend(["-v", "--rmi", "local"])
            print(f"Cleaning up session {s}")
            subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        shutil.rmtree(TEMP_DIRECTORY)
        print("Done.")

def sessions(verbose):
    sessions = get_all_sessions()
    if (sessions):
        for s in sessions:
            if (verbose):
                print(f"{s}    {sessions[s]}")
            else:
                print(s)

# Main function

def main():
    parser = argparse.ArgumentParser(description="Manage virtual lab with Docker + Ansible")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # START
    start_parser = subparsers.add_parser("start", help="Start the virtual lab")
    start_parser.add_argument("-i", "--inventory", required=True, help="Inventory YAML file or directory path")

    # RUN
    run_parser = subparsers.add_parser("run", help="Run playbook or ping hosts")
    run_parser.add_argument("-t", "--test", help="Optional playbook path")
    run_parser.add_argument("-i", "--inventory", help="Inventory YAML file or directory path")
    run_parser.add_argument("-s", "--session", help="The session ID, optional if only one session")

    # STOP
    stop_parser = subparsers.add_parser("stop", help="Stop the virtual lab")
    stop_parser.add_argument("-r", "--rmi", help="Remove docker images", action="store_true")

    # SESSIONS
    session_parser = subparsers.add_parser("sessions", help="Show all the active sessions")
    session_parser.add_argument("-v", "--verbose", help="Show all the infos about a session", action="store_true")

    args = parser.parse_args()

    global INVENTORY, TEST_PATH
    INVENTORY = getattr(args, "inventory", None)
    TEST_PATH = getattr(args, "test", None)
    sessionId = getattr(args, "session", None)


    if args.command == "start":
        start(INVENTORY)
    elif args.command == "run":
        run(INVENTORY, TEST_PATH, sessionId)
    elif args.command == "stop":
        stop(args.rmi)
    elif args.command == "sessions":
        sessions(args.verbose)


if __name__ == "__main__":
    main()
