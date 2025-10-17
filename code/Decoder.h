#ifndef SCREAM_DECODER_H
#define SCREAM_DECODER_H

#include <vector>
#include <cstdint>

class Decoder {
public:
    Decoder(int max_threads = 4);
    ~Decoder();

    // Decode a VP9 frame buffer; returns true on success and fills out_frame (Y,U,V) and sets out_w/out_h
    bool decodeFrame(const std::vector<uint8_t> &vp9_frame, std::vector<uint8_t> &out_frame, int &out_w, int &out_h);

private:
    struct Impl;
    Impl* impl_;
};

#endif // SCREAM_DECODER_H
