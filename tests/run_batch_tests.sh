#!/bin/bash
#
# Automated batch testing script for SCReAM with Mahimahi
#
# Usage: ./run_batch_tests.sh <num_iterations> [output_dir]
#

set -e  # Exit on error

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Paths (adjust if needed)
SCREAM_RX="${SCRIPT_DIR}/../bin/scream_bw_test_rx"
SCREAM_TX="${SCRIPT_DIR}/../bin/scream_bw_test_tx"
MM_DIR="$HOME/projects/mahimahi"  # Mahimahi project directory (for setup script)
MM_SETUP_SCRIPT="${MM_DIR}/setup-mahimahi-delay-routing.sh"
HELPER_SCRIPT="${SCRIPT_DIR}/mahimahi_helper.sh"

# Configuration
NUM_ITERATIONS=${1:-5}
OUTPUT_DIR=${2:-"${SCRIPT_DIR}/logs/bw_test_results_$(date +%Y%m%d_%H%M)"}
DELAY_MS=5
TRACE_FILE="${MM_DIR}/traces/fixed-12mbps.trace"
VIDEO_FILE="$HOME/Downloads/ice_4cif_30fps.y4m"
TEST_DURATION=30
VIDEO_RESOLUTION="704x576"
RX_IP="10.0.0.2"
TX_IP="10.0.0.1"
PORT=8080



echo "=== SCReAM Batch Test Runner ==="
echo "Iterations: $NUM_ITERATIONS"
echo "Output directory: $OUTPUT_DIR"
echo "Delay: ${DELAY_MS}ms"
echo "Test duration: ${TEST_DURATION}s"
echo ""

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Function to kill any lingering scream processes
cleanup_scream() {
    echo "Cleaning up any existing scream processes..."
    pkill -f scream_bw_test_rx || true
    pkill -f scream_bw_test_tx || true
    sleep 1
}

# Function to run a single test iteration
run_test() {
    local iteration=$1
    local log_prefix="${OUTPUT_DIR}/test_${iteration}"
    local signal_start="/tmp/mahimahi_start_rx_$$"
    local signal_rx_ready="/tmp/mahimahi_rx_ready_$$"
    local signal_done="/tmp/mahimahi_done_$$"
    
    echo ""
    echo "====================================================="
    echo "Starting test iteration $iteration of $NUM_ITERATIONS"
    echo "====================================================="
    
    # Clean up any previous processes and signal files
    cleanup_scream
    rm -f "$signal_start" "$signal_rx_ready" "$signal_done"
    
    # Start mahimahi in background, it will signal when to start receiver
    echo "Starting mahimahi shell..."
    mm-delay $DELAY_MS \
        mm-link --uplink-queue=droptail --uplink-queue-args="packets=100" \
        "$TRACE_FILE" "$TRACE_FILE" \
        -- bash "$HELPER_SCRIPT" \
            "$RX_IP" "$TX_IP" "$PORT" "$VIDEO_RESOLUTION" \
            "$VIDEO_FILE" "$TEST_DURATION" "$log_prefix" \
            "$SCREAM_RX" "$SCREAM_TX" "$MM_SETUP_SCRIPT" "$$" \
        > /dev/null 2>&1 &
    
    MAHIMAHI_PID=$!
    echo "Mahimahi shell PID: $MAHIMAHI_PID"
    
    # Wait for signal to start receiver
    echo "Waiting for mahimahi setup to complete..."
    timeout 15 bash -c "while [ ! -f '$signal_start' ]; do sleep 0.1; done" || {
        echo "ERROR: Mahimahi setup timeout!"
        kill $MAHIMAHI_PID 2>/dev/null || true
        cleanup_scream
        return 1
    }
    
    echo "Mahimahi ready, starting receiver..."
    $SCREAM_RX -video $VIDEO_RESOLUTION $RX_IP $PORT \
        > "${log_prefix}_rx.log" 2>&1 &
    RX_PID=$!
    echo "Receiver PID: $RX_PID"
    
    # Give receiver time to bind
    sleep 2
    
    # Signal that receiver is ready
    touch "$signal_rx_ready"
    echo "Receiver ready, sender will start..."
    
    # Wait for mahimahi to complete (sender finishes)
    wait $MAHIMAHI_PID || true
    
    echo "Mahimahi shell exited, stopping receiver..."
    
    # Kill the receiver
    kill $RX_PID 2>/dev/null || true
    wait $RX_PID 2>/dev/null || true
    
    # Cleanup
    cleanup_scream
    rm -f "$signal_start" "$signal_rx_ready" "$signal_done"
    
    echo "Test iteration $iteration completed!"
    echo "Logs saved to: ${log_prefix}_*.log"
    
    # Brief pause between iterations
    sleep 3
}

# Main test loop
echo "Starting batch tests..."
cleanup_scream

for i in $(seq 1 $NUM_ITERATIONS); do
    run_test $i
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
