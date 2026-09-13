#!/usr/bin/env bash
set -uo pipefail

RUN_ID="${1:?run_id}"
OUT_DIR="${2:?out_dir}"

IFACE="eth0"
SRC="192.168.50.10"
DST="192.168.50.20"
PORT=22
ATTEMPTS="${PHASE17D_SSH_ATTEMPTS:-60}"

mkdir -p "$OUT_DIR"
PCAP="$OUT_DIR/$RUN_ID.pcap"
CSV="$OUT_DIR/$RUN_ID.csv"
LOG="$OUT_DIR/$RUN_ID.attempts.log"
TLOG="$OUT_DIR/$RUN_ID.tcpdump.log"
: > "$LOG"

echo "[17d-ssh-v3] run=$RUN_ID iface=$IFACE $SRC -> $DST:$PORT attempts=$ATTEMPTS"
STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

tcpdump -i "$IFACE" -U -w "$PCAP" "host $DST and port $PORT" >/dev/null 2>"$TLOG" &
TCPDUMP_PID=$!

READY=0
for _ in $(seq 1 20); do
  if ! kill -0 "$TCPDUMP_PID" 2>/dev/null; then break; fi
  if grep -q "listening on" "$TLOG" 2>/dev/null; then READY=1; break; fi
  sleep 0.5
done
if [ "$READY" -ne 1 ]; then
  echo "FAILURE tcpdump_not_ready"
  cat "$TLOG" || true
  kill "$TCPDUMP_PID" 2>/dev/null || true
  exit 3
fi

OPENED=0
for i in $(seq 1 "$ATTEMPTS"); do
  if timeout 5 bash -c '
      exec 3<>/dev/tcp/'"$DST"'/'"$PORT"' || exit 1
      printf "SSH-2.0-eval-client-%s\r\n" "'"$i"'" >&3
      head -c 128 <&3 >/dev/null 2>&1 || true
      exec 3<&- 3>&-
    '; then
    OPENED=$((OPENED + 1))
    echo "attempt $i CONNECTED" >> "$LOG"
  else
    echo "attempt $i FAILED rc=$?" >> "$LOG"
  fi
done

sleep 2
kill -INT "$TCPDUMP_PID" 2>/dev/null || true
wait "$TCPDUMP_PID" 2>/dev/null || true
STOPPED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

PCAP_BYTES=$(stat -c%s "$PCAP" 2>/dev/null || echo 0)
if [ "$PCAP_BYTES" -le 24 ]; then
  echo "FAILURE pcap_header_only bytes=$PCAP_BYTES opened=$OPENED"
  exit 4
fi

SYN=$(tcpdump -r "$PCAP" "tcp[tcpflags] & tcp-syn != 0 and dst port $PORT" 2>/dev/null | wc -l)

cicflowmeter -f "$PCAP" -c "$CSV"

CSV_ROWS=0
if [ -f "$CSV" ]; then CSV_ROWS=$(($(wc -l < "$CSV") - 1)); fi
if [ "$CSV_ROWS" -lt 1 ]; then
  echo "FAILURE csv_no_rows opened=$OPENED pcap_bytes=$PCAP_BYTES"
  exit 5
fi

echo "PHASE17D_CAPTURE_RESULT"
echo "run_id=$RUN_ID"
echo "scenario=ssh"
echo "procedure=phase17d_ssh_capture_v3.sh"
echo "capture_attempt=3"
echo "ssh_attempts_planned=$ATTEMPTS"
echo "ssh_connections_opened=$OPENED"
echo "syn_to_dst_port=$SYN"
echo "pcap_bytes=$PCAP_BYTES"
echo "csv_rows=$CSV_ROWS"
echo "started_utc=$STARTED"
echo "stopped_utc=$STOPPED"
echo "pcap=$PCAP"
echo "csv=$CSV"
echo "pcap_sha256=$(sha256sum "$PCAP" | cut -d' ' -f1)"
echo "csv_sha256=$(sha256sum "$CSV" | cut -d' ' -f1)"
echo "extractor=cicflowmeter/0.5.0"
