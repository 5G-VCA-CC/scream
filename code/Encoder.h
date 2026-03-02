#ifndef SCREAM_ENCODER_H
#define SCREAM_ENCODER_H

#include <vector>
#include <cstdint>

class Encoder {
public:
    Encoder(int width, int height, int framerate, unsigned int bitrate_kbps);
    ~Encoder();

    // Encode a single YUV420p frame (Y plane then U then V). Returns encoded bytes (VP9 bitstream)
    std::vector<uint8_t> encodeFrame(const std::vector<uint8_t> &yuv_frame);

    // Update target bitrate (kbps)
    void setBitrate(unsigned int bitrate_kbps);

    // Enable periodic key frames (interval in microseconds)
    void setPeriodicKeyframes(bool enable, uint64_t interval_us = 2000000);

    // Force the next encoded frame to be a key frame (resets after use)
    void forceNextKeyframe();

private:
    struct Impl;
    Impl* impl_;
};

#endif // SCREAM_ENCODER_H
