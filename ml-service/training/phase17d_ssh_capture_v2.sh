#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${1:?run_id}"
OUT_DIR="${2:?out_dir}"

IFACE="eth0"
SRC="192.168.50.10"
DST="192.168.50.20"
ATTEMPTS=60

mkdir -p "$OUT_DIR"
PCAP="$OUT_DIR/$RUN_ID.pcap"
CSV="$OUT_DIR/$RUN_ID.csv"

echo "[17d-ssh-v2] run=$RUN_ID iface=$IFACE $SRC -> $DST:22 attempts=$ATTEMPTS"
STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

tcpdump -i "$IFACE" -w "$PCAP" "host $DST and port 22" >/dev/null 2>&1 &
TCPDUMP_PID=$!
trap 'kill "$TCPDUMP_PID" 2>/dev/null || true' EXIT
sleep 3

for i in $(seq 1 "$ATTEMPTS"); do
  sshpass -p "eval-nonsecret-$i" ssh \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o ConnectTimeout=5 \
    -o PreferredAuthentications=password \
    -o PubkeyAuthentication=no \
    -o NumberOfPasswordPrompts=1 \
    -o KexAlgorithms=+diffie-hellman-group1-sha1,diffie-hellman-group14-sha1 \
    -o HostKeyAlgorithms=+ssh-rsa,ssh-dss \
    -o Ciphers=+aes128-cbc,3des-cbc \
    -o MACs=+hmac-md5,hmac-sha1 \
    "eval-testuser@$DST" 'exit' >/dev/null 2>&1 || true
done

sleep 3
kill "$TCPDUMP_PID" 2>/dev/null || true
wait "$TCPDUMP_PID" 2>/dev/null || true
trap - EXIT
STOPPED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cicflowmeter -f "$PCAP" -c "$CSV"

echo "PHASE17D_CAPTURE_RESULT"
echo "run_id=$RUN_ID"
echo "scenario=ssh"
echo "procedure=phase17d_ssh_capture_v2.sh"
echo "capture_attempt=2"
echo "ssh_attempts=$ATTEMPTS"
echo "started_utc=$STARTED"
echo "stopped_utc=$STOPPED"
echo "pcap=$PCAP"
echo "csv=$CSV"
echo "pcap_sha256=$(sha256sum "$PCAP" | cut -d' ' -f1)"
echo "csv_sha256=$(sha256sum "$CSV" | cut -d' ' -f1)"
echo "extractor=cicflowmeter/0.5.0"
