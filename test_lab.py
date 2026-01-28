import yaml
import subprocess
import sys
import time
import os
import argparse

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


def generate_docker_compose(data):
    """Generate docker-compose.yml dictionary from inventory data."""
    docker_compose = {"services": {}}
    root = data.get("test_inv", data)
    children = root.get("children", {})

    for group in children.values():
        for host, vars in group.get("hosts", {}).items():
            port = vars.get("ansible_port")
            if not port:
                continue

            docker_compose["services"][host] = {
                "build": "./build",
                "container_name": host,
                "command": "/usr/sbin/sshd -D",
                "ports": [f"{port}:22"],
                "networks": ["lab-net"],
                "deploy": {
                    "resources": {
                        "limits": {"cpus": "1.0", "memory": "512M"}
                    }
                },
            }

    docker_compose["networks"] = {"lab-net": {"driver": "bridge"}}
    return docker_compose

def fix_hosts():
    """Fix /etc/hosts in all running containers."""
    container_ids = subprocess.check_output(
        ["docker", "compose", "ps", "-q"]
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

def main():
    parser = argparse.ArgumentParser(description="Run virtual lab with Docker + Ansible")
    parser.add_argument("-i", "--inventory", required=True, help="Inventory YAML file or directory path")
    parser.add_argument("-t", "--test", help="Optional playbook path")
    args = parser.parse_args()

    INVENTORY = args.inventory
    TEST_PATH = args.test

    print("Loading inventory...")
    try:
        data = load_inventory(INVENTORY)
    except Exception as e:
        print(f"Error reading inventory: {e}")
        sys.exit(1)

    print("Generating docker-compose.yml...")
    docker_compose = generate_docker_compose(data)

    with open("docker-compose.yml", "w") as f:
        yaml.dump(docker_compose, f, sort_keys=False)

    print("Starting containers...")
    try:
        subprocess.run(
            ["docker", "compose", "up", "-d", "--build"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        print("Error starting Docker containers")
        os.remove("docker-compose.yml")
        sys.exit(1)

    print("Waiting for SSH stabilization (5s)...")
    time.sleep(5)

    print("Fixing /etc/hosts in containers...")
    fix_hosts()

    if TEST_PATH:
        print(f"Running playbook {TEST_PATH}...")
        subprocess.run(
            ["ansible-playbook", "-i", INVENTORY, TEST_PATH, "-e", "h=all"]
        )
    else:
        print("Pinging all hosts with Ansible...")
        subprocess.run(["ansible", "all", "-m", "ping", "-i", INVENTORY])

    print("Cleaning up...")
    subprocess.run(
        ["docker", "compose", "down", "-v", "--rmi", "local"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.remove("docker-compose.yml")
    print("Done.")

if __name__ == "__main__":
    main()
