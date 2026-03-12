#ifndef SCREAM_ENCODER_H
#define SCREAM_ENCODER_H

#include <vector>
#include <cstdint>
#include "ScreamTx.h"

class Encoder {
public:
    Encoder(int width, int height, int framerate, unsigned int bitrate_kbps, ScreamV2Tx* screamTx, uint32_t ssrc);
    ~Encoder();

    // Encode a single YUV420p frame (Y plane then U then V). Returns encoded bytes (VP9 bitstream)
    std::vector<uint8_t> encodeFrame(const std::vector<uint8_t> &yuv_frame);

    // Update target bitrate (kbps)
    void setBitrate(unsigned int bitrate_kbps);

    // Enable periodic key frames (interval in microseconds)
    void setPeriodicKeyframes(bool enable, uint64_t interval_us = 2000000);

    // Enable feedback-timeout key frames (emulates ringmaster's MAX_UNACKED_US).
    // Forces a key frame when RTCP feedback has been absent for timeout_us microseconds.
    void setFeedbackTimeoutKeyframes(bool enable, uint64_t timeout_us = 1000000);

    // Notify the encoder that RTCP feedback was just received (resets the timeout clock).
    // Called from the RTCP receive path.
    void notifyFeedbackReceived();

    // Force the next encoded frame to be a key frame (resets after use)
    void forceNextKeyframe();

private:
    struct Impl;
    Impl* impl_;
};

#endif // SCREAM_ENCODER_H
