#ifndef SCREAM_ENCODER_H
#define SCREAM_ENCODER_H

#include <vector>
#include <cstdint>

class RtpQueue;
class ScreamV2Tx;

class Encoder {
public:
    Encoder(int width, int height, int framerate, unsigned int bitrate_kbps);
    ~Encoder();

    // Encode a single YUV420p frame (Y plane then U then V). Returns encoded bytes (VP9 bitstream)
    std::vector<uint8_t> encodeFrame(const std::vector<uint8_t> &yuv_frame);

    // Update target bitrate (kbps)
    void setBitrate(unsigned int bitrate_kbps);

    size_t packetize_encoded_frame(const std::vector<uint8_t>& encoded_frame, 
                                    uint32_t ts,
                                    uint32_t time_ntp,
                                    uint32_t ssrc,
                                    int mtu,
                                    uint16_t &seq_nr,
                                    RtpQueue* rtp_queue,
                                    ScreamV2Tx* screamTx);

private:
    struct Impl;
    Impl* impl_;
};

#endif // SCREAM_ENCODER_H
