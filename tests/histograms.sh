#!/bin/bash
#
# Plot sender and receiver histograms for a completed batch run.
#
# Usage:
#   ./histograms.sh <output_dir>
#
# Expects optional metadata in:
#   <output_dir>/histogram_config.env
#
# If metadata is missing, receiver histograms are still generated.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    echo "Usage: $0 <output_dir>"
}

if [ $# -ne 1 ]; then
    usage
    exit 1
fi

OUTPUT_DIR="$1"
if [ ! -d "$OUTPUT_DIR" ]; then
    echo "ERROR: output directory not found: $OUTPUT_DIR"
    exit 1
fi

CONFIG_FILE="${OUTPUT_DIR}/histogram_config.env"

# Optional defaults; populated from config when available.
L4S_ENABLED=""
DELAY_MS=""
LOSS_PCT=""
UPLINK_TRACE_FILE=""
MODE="fake"
VIDEO_FILE=""

if [ -f "$CONFIG_FILE" ]; then
    # shellcheck source=/dev/null
    source "$CONFIG_FILE"
else
    echo "WARNING: Config not found: $CONFIG_FILE"
    echo "         Sender histogram requires config values and will be skipped."
fi

PLOTS_DIR="${OUTPUT_DIR}/plots"
SENDER_PLOTS_DIR="${PLOTS_DIR}/sender"
RECEIVER_PLOTS_DIR="${PLOTS_DIR}/receiver"
mkdir -p "$SENDER_PLOTS_DIR" "$RECEIVER_PLOTS_DIR"
export MPLBACKEND=Agg

if [ -n "$L4S_ENABLED" ] && [ -n "$DELAY_MS" ] && [ -n "$LOSS_PCT" ] && [ -n "$UPLINK_TRACE_FILE" ]; then
    HIST_CMD=(python3 "${SCRIPT_DIR}/plot_scream_histogram.py" \
        "$L4S_ENABLED" "$DELAY_MS" "$LOSS_PCT" "$UPLINK_TRACE_FILE" \
        "$OUTPUT_DIR" "${PLOTS_DIR}/sender" \
        --no-show)

    if [ "$MODE" = "video" ] && [ -n "$VIDEO_FILE" ]; then
        HIST_CMD+=(--video "$VIDEO_FILE")
    fi

    "${HIST_CMD[@]}"
else
    echo "WARNING: Missing sender histogram config in $CONFIG_FILE"
    echo "         Expected: L4S_ENABLED, DELAY_MS, LOSS_PCT, UPLINK_TRACE_FILE"
    echo "         Skipping sender histogram."
fi

python3 "${SCRIPT_DIR}/plot_receiver_histogram.py" \
    "$OUTPUT_DIR" \
    "${PLOTS_DIR}/receiver_summary" \
    --no-show

echo "Histogram plots saved in: $PLOTS_DIR"
