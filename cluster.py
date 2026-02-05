#!/usr/bin/env python3

import yaml
import subprocess
import sys
import os
import argparse
import json
import shutil
import socket
import logging
from pathlib import Path

TEMP_DIRECTORY = Path.home() / ".config/ansible-sample-conf"
MEMO_FILE = f"{TEMP_DIRECTORY}/cluster_session.json"
DOCKERFILES_DIRECTORY = "./Dockerfiles"
DEBUG_LEVEL = 0

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
    """Generate docker-compose.yml dictionary from inventory data with dynamic subnet."""
    docker_compose = {"services": {}}
    root = data.get("test_inv", data)
    vars = root.get("vars", {})
    dockerfile = vars.get("dockerfile")
    children = root.get("children", {})

    try:
        session_num = int(sessionId[1:])
    except ValueError:
        session_num = 0
    
    subnet_prefix = f"172.{19 + session_num}" 
    
    host_ip_map = {}
    ip_counter = 2
    for group in children.values():
        for host in group.get("hosts", {}).keys():
            host_ip_map[host] = f"{subnet_prefix}.0.{ip_counter}"
            ip_counter += 1

    all_extra_hosts = [f"{name}:{ip}" for name, ip in host_ip_map.items()]
    
    for group in children.values():
        for host, host_vars in group.get("hosts", {}).items():
            assigned_ip = host_ip_map[host]
            docker_image = (host_vars.get("dockerfile") if host_vars else None) or dockerfile
            create_docker_images(docker_image, sessionId)

            service_config = {
                "image": f"{docker_image}:latest",
                "container_name": f"{sessionId}-{host}",
                "hostname": host,
                "extra_hosts": [h for h in all_extra_hosts if not h.startswith(f"{host}:")],
                "tmpfs": ["/run", "/run/lock"],
                "networks": {
                    f"{sessionId}-cluster-net": {
                        "ipv4_address": assigned_ip
                    }
                },
                "deploy": {
                    "resources": {
                        "limits": {"cpus": "1.0", "memory": "512M"}
                    }
                },
            }

            if host_vars:
                if host_vars.get("is_entry_point"):
                    port = host_vars.get("ansible_port")
                    update_session(sessionId, entryIp=assigned_ip)
                    if port:
                        host_port = session_port_offset(port, sessionId)
                        service_config["ports"] = [f"{host_port}:22"]
                    else:
                        raise ValueError(f"Entry point {host} missing ansible_port")

            docker_compose["services"][host] = service_config

    docker_compose["networks"] = {
        f"{sessionId}-cluster-net": {
            "driver": "bridge",
            "ipam": {
                "config": [{"subnet": f"{subnet_prefix}.0.0/16"}]
            }
        }
    }
    return docker_compose

def is_port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except:
        return False

# logging

def setup_logging(quiet=False, debug=0):
    if quiet:
        level = logging.ERROR
    elif debug >= 1:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s"
    )

def run_cmd(cmd):
    logging.debug(f"Running command: {' '.join(cmd)}")

    return subprocess.run(
        cmd,
        check=True,
        stdout=None if DEBUG_LEVEL >= 2 else subprocess.DEVNULL,
        stderr=None if DEBUG_LEVEL >= 2 else subprocess.DEVNULL
    )

# docker images

def create_docker_images(dockerfile, sessionId):
    image_name = dockerfile
    dockerfile_path = os.path.join(DOCKERFILES_DIRECTORY, f"Dockerfile.{dockerfile}")
    logging.debug(f"Building docker image '{dockerfile}'")
    run_cmd(["docker", "build", "-t", image_name, "-f", dockerfile_path, "."])

# session

def create_session(path):
    sessions = {}

    if os.path.exists(MEMO_FILE):
        with open(MEMO_FILE, "r") as f:
            try:
                sessions = json.load(f)
            except json.JSONDecodeError:
                sessions = {}

    if sessions:
        numbers = [int(s[1:]) for s in sessions if s.startswith("S") and s[1:].isdigit()]
        next_number = max(numbers) + 1 if numbers else 1
    else:
        next_number = 1

    new_session = f"S{next_number:02d}"
    sessions[new_session] = {"path": path}

    with open(MEMO_FILE, "w") as f:
        json.dump(sessions, f)

    return new_session

def update_session(sessionId, path=None, entryIp=None):
    sessions = get_all_sessions() or {}
    session_data = sessions.get(sessionId, {"path": None, "entryIp": "0.0.0.0"})

    if path is not None: session_data["path"] = path
    if entryIp is not None: session_data["entryIp"] = entryIp

    sessions[sessionId] = session_data

    with open(MEMO_FILE, "w") as f:
        json.dump(sessions, f, indent=2)

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
    vars_root = root.get("vars", {})
    ansible_pass = vars_root.get("ansible_ssh_pass", "password")
    
    jump_host_base_port = 22
    for group in root.get("children", {}).values():
            for host_name, host_vars in group.get("hosts", {}).items():
                if host_vars and host_vars.get("is_entry_point") is True:
                    jump_host_base_port = host_vars.get("ansible_port", 22)
                    break
    
    jump_port = session_port_offset(jump_host_base_port, sessionId)
    ansible_user = vars_root.get("ansible_user", "ubuntu")

    session_root = {
        "vars": {**vars_root},
        "children": {}
    }

    for group_name, group in root.get("children", {}).items():
        session_root["children"][group_name] = {"hosts": {}}

        for host, host_vars in group.get("hosts", {}).items():
            if host_vars:
                new_vars = {**host_vars}
            else:
                new_vars = {}

            if host_vars and host_vars.get("is_entry_point"):
                new_vars["ansible_host"] = "127.0.0.1"
                new_vars["ansible_port"] = jump_port
                new_vars["ansible_ssh_common_args"] = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
            else:
                new_vars["ansible_host"] = host
                new_vars["ansible_port"] = 22

                proxy_cmd = f"ssh -W %h:%p -q {ansible_user}@127.0.0.1 -p {jump_port} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
                new_vars["ansible_ssh_common_args"] = f"-o ProxyCommand='sshpass -p {ansible_pass} {proxy_cmd}'"

            session_root["children"][group_name]["hosts"][host] = new_vars

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
    logging.debug(f"Using inventory: {inventory}")
    sessionId = create_session(inventory)
    logging.info(f"Your session id is {sessionId}")

    logging.debug("Loading inventory...")
    try:
        data = load_inventory(inventory)
    except Exception:
        logging.exception("Error reading inventory")
        sys.exit(1)

    logging.debug("Generating docker-compose.yml...")
    docker_compose = generate_docker_compose(data, sessionId)

    logging.debug("Generating session inventory...")
    session_inventory_path = f"{TEMP_DIRECTORY}/inventory-{sessionId}.yml"
    generate_session_inventory(data, sessionId, session_inventory_path)

    update_session(sessionId, session_inventory_path)

    with open(f"{TEMP_DIRECTORY}/docker-compose-{sessionId}.yml", "w") as f:
        yaml.dump(docker_compose, f, sort_keys=False)

    logging.info("Starting containers...")
    try:
        run_cmd([
                "docker", "compose",
                "-p", sessionId.lower(),
                "-f", f"{TEMP_DIRECTORY}/docker-compose-{sessionId}.yml",
                "up", "-d", "--build"
            ])
    except subprocess.CalledProcessError:
        logging.error("Error starting Docker containers")
        sys.exit(1)

def run(inventory, test_path, sessionId):
    sessions = get_all_sessions()

    if not sessions:
        logging.error("Error: no active session found. Please start a session first.")
        sys.exit(1)

    if sessionId:
        if sessionId not in sessions:
            logging.error(f"Error: session {sessionId} does not exist")
            sys.exit(1)
    else:
        if len(sessions) == 1:
            sessionId = next(iter(sessions))
        else:
            logging.error("Error: multiple sessions found, please specify one with -s")
            sys.exit(1)

    if inventory:
        update_session(sessionId, inventory)
    else:
        inventory = sessions.get(sessionId)["path"]
        if not inventory:
            logging.error("Error: no inventory associated with this session")
            sys.exit(1)

    if test_path:
        logging.info(f"Running playbook {test_path} on inventory {inventory} (session {sessionId})...")
        subprocess.run(["ansible-playbook", "-i", inventory, test_path, "-e", "h=all"])
    else:
        logging.info(f"Pinging all hosts in inventory {inventory} (session {sessionId})...")
        subprocess.run(["ansible", "all", "-m", "ping", "-i", inventory])

def stop():
    sessions = get_all_sessions()
    if (sessions):
        for s in sessions:
            logging.info(f"Cleaning up session {s}")
            run_cmd([
                "docker", "compose",
                "-p", s.lower(),
                "-f", f"{TEMP_DIRECTORY}/docker-compose-{s}.yml",
                "down"
            ])
        logging.debug("Removing temp directory")
        shutil.rmtree(TEMP_DIRECTORY)
        
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
    parser = argparse.ArgumentParser(description="Manage virtual cluster with Docker + Ansible")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # START
    start_parser = subparsers.add_parser("start", help="Start the virtual cluster")
    start_parser.add_argument("-i", "--inventory", required=True, help="Inventory YAML file or directory path")

    # RUN
    run_parser = subparsers.add_parser("run", help="Run playbook or ping hosts")
    run_parser.add_argument("-t", "--test", help="Optional playbook path")
    run_parser.add_argument("-i", "--inventory", help="Inventory YAML file or directory path")
    run_parser.add_argument("-s", "--session", help="The session ID, optional if only one session")

    # STOP
    stop_parser = subparsers.add_parser("stop", help="Stop the virtual cluster")

    # SESSIONS
    session_parser = subparsers.add_parser("sessions", help="Show all the active sessions")
    session_parser.add_argument("-v", "--verbose", help="Show all the infos about a session", action="store_true")

    # LOGGING
    parser.add_argument("-q", "--quiet", help="Only print errors", action="store_true")
    parser.add_argument("-d", "--debug", type=int, default=0, metavar="N", help="Debug level (0=info, 1=verbose, 2=commands output)")

    args = parser.parse_args()

    global INVENTORY, TEST_PATH
    INVENTORY = getattr(args, "inventory", None)
    TEST_PATH = getattr(args, "test", None)
    sessionId = getattr(args, "session", None)

    global DEBUG_LEVEL
    DEBUG_LEVEL = args.debug
    setup_logging(args.quiet, args.debug)


    if args.command == "start":
        start(INVENTORY)
    elif args.command == "run":
        run(INVENTORY, TEST_PATH, sessionId)
    elif args.command == "stop":
        stop()
    elif args.command == "sessions":
        sessions(args.verbose)

if __name__ == "__main__":
    main()
