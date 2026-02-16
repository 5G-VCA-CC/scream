#!/bin/bash
#
# Automated batch testing script for SCReAM with Mahimahi
#
# Usage: ./run_batch_tests.sh <l4s_enabled> <num_iterations> <delay_ms> <loss_pct> <trace_file> <test_duration> [output_dir]
#
# Sender is called with: scream_bw_test_tx -time <duration> -mtu 1388 <ip> <port>
# Receiver is called with: scream_bw_test_rx  <ip> <port>
#

set -e  # Exit on error

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Paths (adjust if needed)
SCREAM_RX="${SCRIPT_DIR}/../bin/scream_bw_test_rx"
SCREAM_TX="${SCRIPT_DIR}/../bin/scream_bw_test_tx"
MM_DIR="$HOME/UCSB/mahimahi"  # Mahimahi project directory (for setup script)
MM_SETUP_SCRIPT="${MM_DIR}/setup-mahimahi-delay-loss-routing.sh"
HELPER_SCRIPT="${SCRIPT_DIR}/mahimahi_helper_fake_traffic.sh"

# Parse arguments
if [ $# -lt 5 ]; then
    echo "Usage: $0 <l4s_enabled> <num_iterations> <loss_pct> <trace_file> <video_file> [output_dir]"
    echo ""
    echo "Arguments:"
    echo "  l4s_enabled      : 0 or 1 to disable/enable L4S ECT marking"
    echo "  num_iterations   : Number of test runs to perform"
    echo "  delay_ms         : Link delay in milliseconds (e.g., 5)"
    echo "  loss_pct         : Uplink packet loss percentage (e.g., 0.01 for 1%)"
    echo "  trace_file       : Path to mahimahi trace file"
    echo "  test_duration    : Test duration in seconds (e.g., 30)"
    echo "  output_dir       : (Optional) Directory for logs (default: auto-generated)"
    exit 1
fi

# Configuration
L4S_ENABLED=$1
NUM_ITERATIONS=$2
DELAY_MS=$3
LOSS_PCT=$4
TRACE_FILE=$5
TEST_DURATION=$6
OUTPUT_DIR=${7:-"${SCRIPT_DIR}/logs/bw_test_results_$(date +%Y%m%d_%H%M)"}

# Validation
if [[ "$L4S_ENABLED" != "0" && "$L4S_ENABLED" != "1" ]]; then
    echo "ERROR: l4s_enabled must be 0 or 1 (got: '$L4S_ENABLED')"
    exit 1
fi

# Validate files exist
if [ ! -f "$TRACE_FILE" ]; then
    echo "ERROR: Trace file not found: $TRACE_FILE"
    exit 1
fi

# Fixed parameters
RX_IP="10.0.0.2"
TX_IP="10.0.0.1"
PORT=8080


echo "=== SCReAM Batch Test Runner ==="
echo "L4S enabled: $L4S_ENABLED"
echo "Iterations: $NUM_ITERATIONS"
echo "Delay: ${DELAY_MS}ms"
echo "Loss: ${LOSS_PCT}%"
echo "Trace file: $TRACE_FILE"
echo "Test duration: ${TEST_DURATION}s"
echo "Output directory: $OUTPUT_DIR"
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
        mm-loss uplink $LOSS_PCT \
        mm-link --uplink-queue=dualPI2 --uplink-queue-args="packets=100" \
        "$TRACE_FILE" "$TRACE_FILE" \
        -- bash "$HELPER_SCRIPT" \
            "$RX_IP" "$TX_IP" "$PORT"  \
            "$TEST_DURATION" "$log_prefix" \
            "$SCREAM_RX" "$SCREAM_TX" "$L4S_ENABLED" "$MM_SETUP_SCRIPT" "$$" \
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
    $SCREAM_RX $RX_IP $PORT \
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
