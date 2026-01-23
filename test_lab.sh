#!/bin/bash

INVENTORY=""
TEST_PATH=""

usage() {
  echo "Usage: $0 -i <inventory_path> [-t <playbook_path>]"
  exit 0
}

while getopts "i:t:h" opt; do
  case $opt in
    i) INVENTORY="$OPTARG" ;;
    t) TEST_PATH="$OPTARG" ;;
    h) usage ;;
    *) usage ;;
  esac
done

if [[ -z "$INVENTORY" ]]; then
    echo "Error: Inventory required (-i)"
    usage
fi

echo "Generating Docker configuration..."
echo "services:" > docker-compose.yml
if ! python3 -c "
import yaml, sys
try:
    with open('$INVENTORY', 'r') as f:
        data = yaml.safe_load(f)
    root = data.get('test_inv', data)
    children = root.get('children', {})
    for group in children.values():
        for host, vars in group.get('hosts', {}).items():
            port = vars.get('ansible_port')
            if port:
                print(f'  {host}:')
                print(f'    build: ./build')
                print(f'    container_name: {host}')
                print(f'    cgroup: host')
                print(f'    ports:')
                print(f'      - \"{port}:22\"')
                print(f'    networks:')
                print(f'      - lab-net')
except Exception as e: 
    print(e, file=sys.stderr)
    sys.exit(1)
" >> docker-compose.yml; then
    echo "Error parsing inventory."
    rm -f docker-compose.yml
    exit 1
fi

cat <<EOF >> docker-compose.yml
networks:
  lab-net:
    driver: bridge
EOF

echo "Starting virtual devices..."
if ! docker compose up -d --build > /dev/null 2>&1; then
    echo "Error starting Docker containers."
    rm -f docker-compose.yml
    exit 1
fi

echo "Waiting for SSH stabilization (5s)..."
sleep 5

echo "Fixing /etc/hosts on all running containers..."
for container_id in $(docker compose ps -q); do
    container_name=$(docker inspect -f '{{.Name}}' "$container_id" | sed 's/\///')
    echo "  -> Unmounting /etc/hosts on $container_name"
    docker exec -u root "$container_id" bash -c "cp /etc/hosts /etc/hosts.bak && umount /etc/hosts && mv /etc/hosts.bak /etc/hosts" 2>/dev/null
done

if [[ -n "$TEST_PATH" ]]; then
    ansible-playbook -i "$INVENTORY" "$TEST_PATH" -e "h=all"
else
    ansible all -m ping -i "$INVENTORY"
fi

echo "Cleaning up..."
docker compose down -v --rmi local > /dev/null 2>&1
rm -f docker-compose.yml
echo "Done."