#!/usr/bin/env bash
set -euo pipefail

SCENARIO="${1:?scenario}"
RUN_ID="${2:?run_id}"
OUT_DIR="${3:?out_dir}"

IFACE="eth0"
SRC="192.168.50.10"
DST="192.168.50.20"

mkdir -p "$OUT_DIR"
PCAP="$OUT_DIR/$RUN_ID.pcap"
CSV="$OUT_DIR/$RUN_ID.csv"

echo "[17d] scenario=$SCENARIO run=$RUN_ID iface=$IFACE $SRC -> $DST"
STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

tcpdump -i "$IFACE" -w "$PCAP" "host $DST" >/dev/null 2>&1 &
TCPDUMP_PID=$!
trap 'kill "$TCPDUMP_PID" 2>/dev/null || true' EXIT
sleep 3

case "$SCENARIO" in
  benign)
    for i in $(seq 1 40); do
      ping -c 2 "$DST" >/dev/null 2>&1 || true
      curl -s "http://$DST/" >/dev/null 2>&1 || true
      curl -s "http://$DST/dvwa/" >/dev/null 2>&1 || true
      curl -s "http://$DST/mutillidae/" >/dev/null 2>&1 || true
      curl -s "ftp://ftp:ftp@$DST/" >/dev/null 2>&1 || true
      sshpass -p 'msfadmin' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
        msfadmin@"$DST" 'uname -a; id; ls /' >/dev/null 2>&1 || true
      dig @"$DST" metasploitable.localdomain +time=2 +tries=1 >/dev/null 2>&1 || true
      dig @"$DST" example.test +time=2 +tries=1 >/dev/null 2>&1 || true
    done
    ;;
  portscan)
    for i in $(seq 1 3); do
      nmap -p- -T4 -Pn "$DST" >/dev/null 2>&1 || true
      nmap -sS -p1-65535 -T4 -Pn "$DST" >/dev/null 2>&1 || true
    done
    ;;
  ssh)
    WL="$(mktemp)"
    for i in $(seq 1 60); do echo "eval-nonsecret-$i"; done > "$WL"
    hydra -l eval-testuser -P "$WL" -t 4 -f -o /dev/null \
      "ssh://$DST:22" >/dev/null 2>&1 || true
    rm -f "$WL"
    ;;
  *)
    echo "unknown scenario: $SCENARIO" >&2; exit 2 ;;
esac

sleep 3
kill "$TCPDUMP_PID" 2>/dev/null || true
wait "$TCPDUMP_PID" 2>/dev/null || true
trap - EXIT
STOPPED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cicflowmeter -f "$PCAP" -c "$CSV"

echo "PHASE17D_CAPTURE_RESULT"
echo "run_id=$RUN_ID"
echo "scenario=$SCENARIO"
echo "started_utc=$STARTED"
echo "stopped_utc=$STOPPED"
echo "pcap=$PCAP"
echo "csv=$CSV"
echo "pcap_sha256=$(sha256sum "$PCAP" | cut -d' ' -f1)"
echo "csv_sha256=$(sha256sum "$CSV" | cut -d' ' -f1)"
echo "extractor=cicflowmeter/0.5.0"
