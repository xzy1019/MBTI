#!/bin/sh
# Requires an extracted Docker 26.1.4 static runtime in /opt/mbti-site/runtime/docker.
# Intended for the dedicated, previously empty CentOS 7 host only.
set -eu
if [ -f /etc/docker/daemon.json ] && ! grep -q '/opt/mbti-site/docker-data' /etc/docker/daemon.json; then
    printf '%s\n' 'Existing Docker configuration detected; refusing to overwrite it.' >&2
    exit 1
fi
mkdir -p /etc/docker /opt/mbti-site
cat > /etc/docker/daemon.json <<'JSON'
{"data-root":"/opt/mbti-site/docker-data","storage-driver":"vfs","iptables":false,"bridge":"none","exec-opts":["native.cgroupdriver=cgroupfs"],"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"3"}}
JSON
cat > /etc/systemd/system/mbti-docker.service <<'UNIT'
[Unit]
Description=Self Atlas isolated Docker runtime
After=network.target
[Service]
Type=notify
Environment=PATH=/opt/mbti-site/runtime/docker:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
ExecStart=/opt/mbti-site/runtime/docker/dockerd --config-file=/etc/docker/daemon.json
Restart=on-failure
RestartSec=5
Delegate=yes
LimitNOFILE=1048576
LimitNPROC=infinity
LimitCORE=infinity
TasksMax=infinity
TimeoutStartSec=120
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable mbti-docker
systemctl start mbti-docker
/opt/mbti-site/runtime/docker/docker info --format '{{.ServerVersion}} {{.Driver}}'
date -u
