FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    sudo \
    openssh-server \
    python3 \
    python3-apt \
    iputils-ping \
    vim \
    tzdata \
    unattended-upgrades \
    fwupd \
    logrotate \
    rsyslog \
    uuid-runtime \
    systemd \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir /var/run/sshd && \
    echo 'root:rootpassword' | chpasswd && \
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config

RUN mkdir -p /etc/update-motd.d/ && \
    touch /etc/update-motd.d/10-help-text \
          /etc/update-motd.d/50-motd-news \
          /etc/update-motd.d/85-fwupd \
          /etc/update-motd.d/90-updates-available \
          /etc/update-motd.d/91-contract-ua-esm-status \
          /etc/update-motd.d/91-release-upgrade \
          /etc/update-motd.d/92-unattended-upgrades \
          /etc/update-motd.d/95-hwe-eol && \
    chmod +x /etc/update-motd.d/*

RUN useradd -m -s /bin/bash ubuntu && \
    echo 'ubuntu:password' | chpasswd && \
    adduser ubuntu sudo && \
    echo "ubuntu ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

EXPOSE 22

CMD ["/usr/sbin/sshd", "-D"]