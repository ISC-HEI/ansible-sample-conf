import yaml
import subprocess
import sys
import time
import os
import argparse

parser = argparse.ArgumentParser(description="Run virtual lab with Docker + Ansible")
parser.add_argument("-i", "--inventory", required=True, help="Inventory YAML path")
parser.add_argument("-t", "--test", help="Optional playbook path")
args = parser.parse_args()

INVENTORY = args.inventory
TEST_PATH = args.test

print("Generating docker-compose.yml...")
docker_compose = {"services": {}}

try:
    with open(INVENTORY, "r") as f:
        data = yaml.safe_load(f)
except Exception as e:
    print(f"Error reading inventory: {e}")
    sys.exit(1)

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

with open("docker-compose.yml", "w") as f:
    yaml.dump(docker_compose, f, sort_keys=False)

print("Starting containers...")
try:
    subprocess.run(["docker", "compose", "up", "-d", "--build"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,)
except subprocess.CalledProcessError:
    print("Error starting Docker containers")
    os.remove("docker-compose.yml")
    sys.exit(1)

print("Waiting for SSH stabilization (5s)...")
time.sleep(5)

print("Fixing /etc/hosts in containers...")
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
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

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
