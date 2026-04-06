#!/bin/bash
#
# Unified automated batch testing script for SCReAM with Mahimahi.
#
# Supports both "fake traffic" (rate-based sender) and "video traffic" (sender with video encoder).
# Video parameters are optional; if provided, the script runs in video mode.
#
# Usage:
#   ./run_batch_tests.sh <l4s_enabled> <num_iterations> <delay_ms> <loss_pct> <uplink_trace_file> <downlink_trace_file> <test_duration> [video_file] [video_resolution] [output_dir] [video_fps]
#
# Required:
#   l4s_enabled     : 0 or 1 to disable/enable L4S ECT marking
#   num_iterations  : number of test runs to perform
#   delay_ms        : link delay in milliseconds (e.g., 5)
#   loss_pct        : uplink packet loss rate as decimal (e.g., 0.01 for 1%)
#   uplink_trace_file   : path to mahimahi uplink trace file
#   downlink_trace_file : path to mahimahi downlink trace file
#   test_duration   : test duration in seconds (e.g., 30)
#
# Optional (video mode):
#   video_file       : path to input video file (.y4m)
#   video_resolution : video resolution WxH (e.g., 704x576)
#   video_fps        : sender FPS (default: 30)
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
    $0 <l4s_enabled> <num_iterations> <delay_ms> <loss_pct> <uplink_trace_file> <downlink_trace_file> <test_duration> [video_file] [video_resolution] [output_dir] [video_fps]

    video_fps (video mode only, optional):
        Positive number, e.g. 24, 29.97, 30, 60

Examples:
  # Fake traffic
    $0 1 5 5 0.01 traces/up.txt traces/down.txt 30
    $0 0 3 25 0.00 traces/up.txt traces/down.txt 60 /tmp/results

  # Video traffic
        $0 1 3 5 0.01 traces/up.txt traces/down.txt 30 input.y4m 704x576
        $0 1 3 5 0.01 traces/up.txt traces/down.txt 30 input.y4m 704x576 /tmp/results 30
EOF
}

if [ $# -lt 7 ]; then
    usage
    exit 1
fi

L4S_ENABLED="$1"
NUM_ITERATIONS="$2"
DELAY_MS="$3"
LOSS_PCT="$4"
UPLINK_TRACE_FILE="$5"
DOWNLINK_TRACE_FILE="$6"
TEST_DURATION="$7"
shift 7

VIDEO_FILE=""
VIDEO_RESOLUTION=""
OUTPUT_DIR=""
VIDEO_FPS="30"

# Detect video mode by [video_file] [video_resolution]
if [ $# -ge 2 ] && [[ "$2" =~ ^[0-9]+x[0-9]+$ ]]; then
    VIDEO_FILE="$1"
    VIDEO_RESOLUTION="$2"
    shift 2
fi

if [ -n "$VIDEO_FILE" ]; then
    # Optional output_dir
    if [ $# -ge 1 ] && ! [[ "$1" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
        OUTPUT_DIR="$1"
        shift 1
    fi

    # Optional video_fps
    if [ $# -ge 1 ]; then
        if [[ "$1" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
            VIDEO_FPS="$1"
            shift 1
        else
            echo "ERROR: Invalid video_fps '$1' (expected positive number)"
            exit 1
        fi
    fi
else
    # Fake traffic mode: only optional output_dir is supported
    if [ $# -ge 1 ]; then
        OUTPUT_DIR="$1"
        shift 1
    fi
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

if [ ! -f "$UPLINK_TRACE_FILE" ]; then
    echo "ERROR: Uplink trace file not found: $UPLINK_TRACE_FILE"
    exit 1
fi

if [ ! -f "$DOWNLINK_TRACE_FILE" ]; then
    echo "ERROR: Downlink trace file not found: $DOWNLINK_TRACE_FILE"
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
    if ! awk "BEGIN { exit !($VIDEO_FPS > 0) }"; then
        echo "ERROR: video_fps must be > 0 (got: '$VIDEO_FPS')"
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
echo "Uplink trace file: $UPLINK_TRACE_FILE"
echo "Downlink trace file: $DOWNLINK_TRACE_FILE"
echo "Test duration: ${TEST_DURATION}s"
if [ "$MODE" = "video" ]; then
    echo "Video file: $VIDEO_FILE"
    echo "Video resolution: $VIDEO_RESOLUTION"
    echo "Keyframe policy: hardcoded (-keyframe-on-target -keyframe-unacked)"
    echo "Video FPS: $VIDEO_FPS"
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
    local mm_log="${log_prefix}_mm.log"
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
            "$UPLINK_TRACE_FILE" "$DOWNLINK_TRACE_FILE" \
            -- bash "$HELPER_SCRIPT" \
                "$RX_IP" "$TX_IP" "$PORT" "$VIDEO_RESOLUTION" \
                "$VIDEO_FILE" "$TEST_DURATION" "$log_prefix" \
                "$SCREAM_RX" "$SCREAM_TX" "$L4S_ENABLED" "$MM_SETUP_SCRIPT" "$$" \
                "$VIDEO_FPS" \
            > "$mm_log" 2>&1 &
    else
        mm-delay "$DELAY_MS" \
            mm-loss uplink "$LOSS_PCT" \
            mm-link --uplink-queue=dualPI2 --uplink-queue-args="packets=100[, l4s_max_threshold=10]" \
            "$UPLINK_TRACE_FILE" "$DOWNLINK_TRACE_FILE" \
            -- bash "$HELPER_SCRIPT" \
                "$RX_IP" "$TX_IP" "$PORT" \
                "$TEST_DURATION" "$log_prefix" \
                "$SCREAM_RX" "$SCREAM_TX" "$L4S_ENABLED" "$MM_SETUP_SCRIPT" "$$" \
            > "$mm_log" 2>&1 &
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
        "$SCREAM_RX" -video "$VIDEO_RESOLUTION" "$TX_IP" "$PORT" > "${log_prefix}_rx.log" 2>&1 &
    else
        "$SCREAM_RX" "$TX_IP" "$PORT" > "${log_prefix}_rx.log" 2>&1 &
    fi

    local RX_PID=$!
    echo "Receiver PID: $RX_PID"

    sleep 2
    touch "$signal_rx_ready"
    echo "Receiver ready, sender will start..."

    local wait_timeout
    wait_timeout="$(awk -v d="$TEST_DURATION" 'BEGIN { w=int(d+30); if (w < 30) w=30; print w }')"
    local waited=0
    while kill -0 "$MAHIMAHI_PID" 2>/dev/null; do
        sleep 1
        waited=$((waited + 1))
        if [ "$waited" -ge "$wait_timeout" ]; then
            echo "Mahimahi timed out after ${wait_timeout}s, killing it (see $mm_log)"
            kill -TERM "$MAHIMAHI_PID" 2>/dev/null || true
            sleep 1
            kill -KILL "$MAHIMAHI_PID" 2>/dev/null || true
            break
        fi
    done

    wait "$MAHIMAHI_PID" 2>/dev/null || true

    echo "Mahimahi shell exited, stopping receiver..."
    kill -TERM "$RX_PID" 2>/dev/null || true

    grace_ok=0
    for _ in $(seq 1 30); do
        if ! kill -0 "$RX_PID" 2>/dev/null; then
            grace_ok=1
            break
        fi
        sleep 0.1
    done

    if [ "$grace_ok" -eq 1 ]; then
        wait "$RX_PID" 2>/dev/null || true
    else
        echo "Receiver did not exit in time, forcing kill"
        kill -KILL "$RX_PID" 2>/dev/null || true
        wait "$RX_PID" 2>/dev/null || true
    fi
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
echo "====================================================="
echo "Plotting Results!"
echo "====================================================="
echo "Results saved in: $OUTPUT_DIR"

PLOTS_DIR="${OUTPUT_DIR}/plots"
SENDER_PLOTS_DIR="${PLOTS_DIR}/sender"
RECEIVER_PLOTS_DIR="${PLOTS_DIR}/receiver"
mkdir -p "$SENDER_PLOTS_DIR" "$RECEIVER_PLOTS_DIR"
export MPLBACKEND=Agg

HIST_CMD=(python3 "${SCRIPT_DIR}/plot_scream_histogram.py" \
    "$L4S_ENABLED" "$DELAY_MS" "$LOSS_PCT" "$UPLINK_TRACE_FILE" \
    "$OUTPUT_DIR" "$PLOTS_DIR/sender" \
    --no-show)

if [ "$MODE" = "video" ]; then
    HIST_CMD+=(--video "$VIDEO_FILE")
fi

"${HIST_CMD[@]}"

python3 "${SCRIPT_DIR}/plot_receiver_histogram.py" \
    "$OUTPUT_DIR" \
    "${PLOTS_DIR}/receiver_summary" \
    --no-show

echo ""
echo "To analyze CWND data from all tests:"
echo "  for log in $OUTPUT_DIR/*_tx.log; do"
echo "    python3 tests/plot_scream_cwnd.py \"\$log\""
echo "  done"
