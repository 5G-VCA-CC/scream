#!/bin/bash
#
# Unified automated batch testing script for SCReAM with Mahimahi.
#
# Supports both "fake traffic" (rate-based sender) and "video traffic" (sender with video encoder).
# Video parameters are optional; if provided, the script runs in video mode.
#
# Usage:
#   ./run_batch_tests.sh <l4s_enabled> <num_iterations> <delay_ms> <loss_pct> <trace_file> <test_duration> [video_file] [video_resolution] [output_dir]
#
# Required:
#   l4s_enabled     : 0 or 1 to disable/enable L4S ECT marking
#   num_iterations  : number of test runs to perform
#   delay_ms        : link delay in milliseconds (e.g., 5)
#   loss_pct        : uplink packet loss rate as decimal (e.g., 0.01 for 1%)
#   trace_file      : path to mahimahi trace file
#   test_duration   : test duration in seconds (e.g., 30)
#
# Optional (video mode):
#   video_file       : path to input video file (.y4m)
#   video_resolution : video resolution WxH (e.g., 704x576)
#
# Optional:
#   output_dir      : directory for logs (default: auto-generated)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SCREAM_RX="${SCRIPT_DIR}/../bin/scream_bw_test_rx"
SCREAM_TX="${SCRIPT_DIR}/../bin/scream_bw_test_tx"
MM_DIR="$HOME/UCSB/mahimahi-dualpi2"
MM_SETUP_SCRIPT="${MM_DIR}/setup-mahimahi-delay-loss-routing.sh"

usage() {
    cat <<EOF
Usage:
  $0 <l4s_enabled> <num_iterations> <delay_ms> <loss_pct> <trace_file> <test_duration> [video_file] [video_resolution] [output_dir]

Examples:
  # Fake traffic
  $0 1 5 5 0.01 traces/trace_key.txt 30
  $0 0 3 25 0.00 traces/trace_flat.txt 60 /tmp/results

  # Video traffic
  $0 1 3 5 0.01 traces/trace_key.txt 30 input.y4m 704x576
  $0 1 3 5 0.01 traces/trace_key.txt 30 input.y4m 704x576 /tmp/results
EOF
}

if [ $# -lt 6 ]; then
    usage
    exit 1
fi

L4S_ENABLED="$1"
NUM_ITERATIONS="$2"
DELAY_MS="$3"
LOSS_PCT="$4"
TRACE_FILE="$5"
TEST_DURATION="$6"
shift 6

VIDEO_FILE=""
VIDEO_RESOLUTION=""
OUTPUT_DIR=""

# Optional video args are positional. If the next arg is a file, treat it as video_file.
if [ $# -ge 1 ] && [ -f "$1" ]; then
    VIDEO_FILE="$1"
    if [ $# -lt 2 ]; then
        echo "ERROR: video_resolution (WxH) is required when video_file is provided"
        usage
        exit 1
    fi
    VIDEO_RESOLUTION="$2"
    shift 2
fi

# Optional output dir (remaining single arg)
if [ $# -ge 1 ]; then
    OUTPUT_DIR="$1"
    shift 1
fi

if [ $# -ne 0 ]; then
    echo "ERROR: Too many arguments"
    usage
    exit 1
fi

if [[ "$L4S_ENABLED" != "0" && "$L4S_ENABLED" != "1" ]]; then
    echo "ERROR: l4s_enabled must be 0 or 1 (got: '$L4S_ENABLED')"
    exit 1
fi

if [ ! -f "$TRACE_FILE" ]; then
    echo "ERROR: Trace file not found: $TRACE_FILE"
    exit 1
fi

if [ -n "$VIDEO_FILE" ] && [ ! -f "$VIDEO_FILE" ]; then
    echo "ERROR: Video file not found: $VIDEO_FILE"
    exit 1
fi

if [ -n "$VIDEO_FILE" ]; then
    if ! [[ "$VIDEO_RESOLUTION" =~ ^[0-9]+x[0-9]+$ ]]; then
        echo "ERROR: video_resolution must look like WxH (got: '$VIDEO_RESOLUTION')"
        exit 1
    fi
fi

if [ -z "$OUTPUT_DIR" ]; then
    OUTPUT_DIR="${SCRIPT_DIR}/logs/bw_test_results_$(date +%Y%m%d_%H%M)"
fi

if [ ! -x "$SCREAM_RX" ]; then
    echo "ERROR: SCReAM receiver not found/executable: $SCREAM_RX"
    exit 1
fi

if [ ! -x "$SCREAM_TX" ]; then
    echo "ERROR: SCReAM sender not found/executable: $SCREAM_TX"
    exit 1
fi

if [ ! -f "$MM_SETUP_SCRIPT" ]; then
    echo "ERROR: Mahimahi setup script not found: $MM_SETUP_SCRIPT"
    exit 1
fi

MODE="fake"
HELPER_SCRIPT="${SCRIPT_DIR}/mahimahi_helper_fake_traffic.sh"
if [ -n "$VIDEO_FILE" ]; then
    MODE="video"
    HELPER_SCRIPT="${SCRIPT_DIR}/mahimahi_helper_video_traffic.sh"
fi

RX_IP="10.0.0.2"
TX_IP="10.0.0.1"
PORT=8080

echo "=== SCReAM Batch Test Runner ==="
echo "Mode: $MODE"
echo "L4S enabled: $L4S_ENABLED"
echo "Iterations: $NUM_ITERATIONS"
echo "Delay: ${DELAY_MS}ms"
echo "Loss: ${LOSS_PCT}"
echo "Trace file: $TRACE_FILE"
echo "Test duration: ${TEST_DURATION}s"
if [ "$MODE" = "video" ]; then
    echo "Video file: $VIDEO_FILE"
    echo "Video resolution: $VIDEO_RESOLUTION"
fi
echo "Output directory: $OUTPUT_DIR"
echo ""

mkdir -p "$OUTPUT_DIR"

cleanup_scream() {
    echo "Cleaning up any existing scream processes..."
    pkill -f scream_bw_test_rx || true
    pkill -f scream_bw_test_tx || true
    sleep 1
}

run_test() {
    local iteration="$1"
    local log_prefix="${OUTPUT_DIR}/test_${iteration}"
    local signal_start="/tmp/mahimahi_start_rx_$$"
    local signal_rx_ready="/tmp/mahimahi_rx_ready_$$"
    local signal_done="/tmp/mahimahi_done_$$"

    echo ""
    echo "====================================================="
    echo "Starting test iteration $iteration of $NUM_ITERATIONS"
    echo "====================================================="

    cleanup_scream
    rm -f "$signal_start" "$signal_rx_ready" "$signal_done"

    echo "Starting mahimahi shell..."

    if [ "$MODE" = "video" ]; then
        mm-delay "$DELAY_MS" \
            mm-loss uplink "$LOSS_PCT" \
            mm-link --uplink-queue=dualPI2 --uplink-queue-args="packets=100" \
            "$TRACE_FILE" "$TRACE_FILE" \
            -- bash "$HELPER_SCRIPT" \
                "$RX_IP" "$TX_IP" "$PORT" "$VIDEO_RESOLUTION" \
                "$VIDEO_FILE" "$TEST_DURATION" "$log_prefix" \
                "$SCREAM_RX" "$SCREAM_TX" "$L4S_ENABLED" "$MM_SETUP_SCRIPT" "$$" \
            > /dev/null 2>&1 &
    else
        mm-delay "$DELAY_MS" \
            mm-loss uplink "$LOSS_PCT" \
            mm-link --uplink-queue=dualPI2 --uplink-queue-args="packets=100" \
            "$TRACE_FILE" "$TRACE_FILE" \
            -- bash "$HELPER_SCRIPT" \
                "$RX_IP" "$TX_IP" "$PORT" \
                "$TEST_DURATION" "$log_prefix" \
                "$SCREAM_RX" "$SCREAM_TX" "$L4S_ENABLED" "$MM_SETUP_SCRIPT" "$$" \
            > /dev/null 2>&1 &
    fi

    local MAHIMAHI_PID=$!
    echo "Mahimahi shell PID: $MAHIMAHI_PID"

    echo "Waiting for mahimahi setup to complete..."
    timeout 15 bash -c "while [ ! -f '$signal_start' ]; do sleep 0.1; done" || {
        echo "ERROR: Mahimahi setup timeout!"
        kill "$MAHIMAHI_PID" 2>/dev/null || true
        cleanup_scream
        return 1
    }

    echo "Mahimahi ready, starting receiver..."
    if [ "$MODE" = "video" ]; then
        "$SCREAM_RX" -video "$VIDEO_RESOLUTION" "$RX_IP" "$PORT" > "${log_prefix}_rx.log" 2>&1 &
    else
        "$SCREAM_RX" "$RX_IP" "$PORT" > "${log_prefix}_rx.log" 2>&1 &
    fi

    local RX_PID=$!
    echo "Receiver PID: $RX_PID"

    sleep 2
    touch "$signal_rx_ready"
    echo "Receiver ready, sender will start..."

    wait "$MAHIMAHI_PID" || true

    echo "Mahimahi shell exited, stopping receiver..."
    kill "$RX_PID" 2>/dev/null || true
    wait "$RX_PID" 2>/dev/null || true

    cleanup_scream
    rm -f "$signal_start" "$signal_rx_ready" "$signal_done"

    echo "Test iteration $iteration completed!"
    echo "Logs saved to: ${log_prefix}_*.log"

    sleep 3
}

echo "Starting batch tests..."
cleanup_scream

for i in $(seq 1 "$NUM_ITERATIONS"); do
    run_test "$i"
done

echo ""
echo "====================================================="
echo "All tests completed!"
echo "====================================================="
echo "Results saved in: $OUTPUT_DIR"
echo ""
echo "Log files:"
ls -lh "$OUTPUT_DIR"/*.log

echo ""
echo "To analyze CWND data from all tests:"
echo "  for log in $OUTPUT_DIR/*_tx.log; do"
echo "    python3 tests/plot_scream_cwnd.py \"\$log\""
echo "  done"
