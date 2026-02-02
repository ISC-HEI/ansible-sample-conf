<div align="center">

# Ansible virtual cluster generator

![Linux](https://img.shields.io/badge/Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black)
![Ansible](https://img.shields.io/badge/Ansible-000000?style=for-the-badge&logo=ansible&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-Apache-red.svg?style=for-the-badge)

Dynamically generate isolated Ansible test clusters using Docker Compose,
directly from an Ansible inventory.

This project is designed to safely validate Ansible playbooks without impacting
the real infrastructure.

</div>


## Overview

This tool converts an Ansible inventory into a fully isolated Docker-based cluster:

- Each Ansible host is mapped to a Docker container
- SSH access is preserved
- Port conflicts are avoided using session-based offsets
- Multiple clusters can run in parallel
- No modification is made to the host system

It is especially useful for testing playbooks such as:
https://github.com/ISC-HEI/ansible-playbooks


## Key Features

- Infrastructure-as-Inventory  
  The Ansible inventory defines the entire cluster topology.

- Session-based isolation  
  Each cluster runs in its own session (S01, S02, …).

- Automatic Docker Compose generation  
  No manual Docker configuration is required.

- Playbook execution  
  Run Ansible ping or full playbooks against the cluster.

- Clean lifecycle  
  Start, test, and destroy clusters cleanly.

- Menu for easy utilisation.


## Architecture

Ansible Inventory  
-  Session Inventory (localhost with port offsets)  
- docker-compose.yml  
- Docker containers (SSH enabled)  
- ansible / ansible-playbook execution


## Prerequisites

The following tools are required:

- Docker and Docker Compose
- Python + venv
- Ansible


## Installation

Clone this repository:

```bash
git clone https://github.com/ISC-HEI/ansible-sample-conf.git
cd ansible-sample-conf
```

(Optional) Clone the playbooks repository:

```bash
cd ..
git clone https://github.com/ISC-HEI/ansible-playbooks.git
```

Activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Menu

This repo provied a menu for easy utilisation, start it like that:
```bash
./menu.py
```

### CLI Commands
The entry point for CLI commands is:

```bash
./cluster.py
```


## Start a cluster

Create a new isolated cluster session from an Ansible inventory:

```bash
./cluster.py start -i inventory/inventory.yml
```

This will:

- Create a new session (S01, S02, …)
- Generate a docker-compose file
- Generate a session-specific inventory


## Run Tests or Playbooks

Ping all hosts in the active session:

```bash
./cluster.py run
```

Run a specific playbook:

```bash
./cluster.py run -t path/to/playbook.yml
```

If multiple sessions exist, specify one:

```bash
./cluster.py run -s S02
```


## List Active Sessions

Show all active sessions:

```bash
./cluster.py sessions
```

Verbose mode:

```bash
./cluster.py sessions -v
```


## Stop and Cleanup

Stop all running clusters:

```bash
./cluster.py stop
```

Stop clusters and remove Docker images:

```bash
./cluster.py stop --rmi
```


## Example Workflow

```bash
./cluster.py start -i inventory/inventory.yml
./cluster.py run
./cluster.py run -t playbooks/site.yml
./cluster.py stop
```


## Inventory Notes

- Supports a single YAML inventory file or a directory of YAML files
- Hosts must define ansible_port
- SSH access is exposed on localhost with a session-based port offset
- The inventory is automatically rewritten for local execution

Minimal example:

```yaml
web01:
  ansible_port: 22
```


## Important Limitations

Because Docker containers share the host kernel:

- Kernel modules (modprobe) will not work
- Low-level system operations may behave differently
- Docker images are minimal and may require additional packages

You can customize the images in:

```text
Dockerfiles/Dockerfile.*
```


## License

Apache License 2.0


## Related Projects

Ansible Playbooks:
https://github.com/ISC-HEI/ansible-playbooks
