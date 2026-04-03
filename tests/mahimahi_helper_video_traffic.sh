#!/bin/bash
#
# Helper script that runs INSIDE mahimahi shell
# Starts receiver on host, then runs sender within mahimahi
#

set -e

# Configuration passed from parent script
RX_IP="$1"
TX_IP="$2"
PORT="$3"
VIDEO_RESOLUTION="$4"
VIDEO_FILE="$5"
TEST_DURATION="$6"
LOG_PREFIX="$7"
SCREAM_RX="$8"
SCREAM_TX="$9"
L4S_ENABLED="${10}"
SETUP_SCRIPT="${11}"
PARENT_PID="${12}"  # Parent script's PID for signal files

echo "=== Inside Mahimahi Shell ==="
echo "Setting up routing..."
$SETUP_SCRIPT

# Now that mahimahi network is set up, signal parent to start receiver
echo "Signaling parent to start receiver..."
# Create a signal file for the parent to start receiver
SIGNAL_START="/tmp/mahimahi_start_rx_${PARENT_PID}"
SIGNAL_RX_READY="/tmp/mahimahi_rx_ready_${PARENT_PID}"

# Signal parent to start receiver
touch "$SIGNAL_START"

# Wait for receiver to be ready (parent will create this file)
echo "Waiting for receiver to be ready..."
timeout 10 bash -c "while [ ! -f '$SIGNAL_RX_READY' ]; do sleep 0.1; done" || {
    echo "ERROR: Receiver failed to start within 10 seconds timeout"
    exit 1
}

echo "Receiver is ready, starting sender..."
$SCREAM_TX -ect "$L4S_ENABLED" -video "$VIDEO_FILE" -fps 30 -time "$TEST_DURATION" -losskey "$TX_IP" "$PORT" \
    > "${LOG_PREFIX}_tx.log" 2>&1

echo "Sender completed."

# Signal that we're done (optional)
touch "/tmp/mahimahi_done_${PARENT_PID}"