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

    // Reinitialize the decoder context (used after corruption/loss)
    void reset();

    // Lightweight probe to determine whether the provided frame is a key frame
    bool isKeyFrame(const std::vector<uint8_t> &vp9_frame) const;

private:
    struct Impl;
    Impl* impl_;
    void initContext();
};

#endif // SCREAM_DECODER_H
