#ifndef SCREAM_ENCODER_H
#define SCREAM_ENCODER_H

#include <vector>
#include <cstdint>
#include <pthread.h>
#include <map>
#include <optional>
#include <memory>
#include <mutex>

#include "ScreamTx.h"
#include "RtpQueue.h"

class Encoder {
public:
    Encoder(int width,
            int height,
            int framerate,
            unsigned int bitrate_kbps,
            ScreamV2Tx* screamTx,
            pthread_mutex_t* lock_scream,
            uint32_t ssrc);
    ~Encoder();

    // Encode a single YUV420p frame (Y plane then U then V).
    // Returns encoded bytes (VP9 bitstream)
    std::vector<uint8_t> encodeFrame(const std::vector<uint8_t> &yuv_frame);

    // Update target bitrate (kbps)
    void setBitrate(unsigned int bitrate_kbps);

    // Enable periodic key frames (interval in microseconds)
    void setPeriodicKeyframes(bool enable, uint64_t interval_us = 2000000);

    // Enable feedback-timeout key frames
    void setFeedbackTimeoutKeyframes(bool enable, uint64_t timeout_us = 1000000);

    // Notify the encoder that RTCP feedback was just received
    void notifyFeedbackReceived();

    // Force the next encoded frame to be a key frame
    void forceNextKeyframe();

    // Add a transmitted but unacked RTP packet
    // NOTE: This should be called only for original transmissions, not retransmissions.
    void addUnacked(void* pkt,
                    int size,
                    uint32_t frame_id,
                    uint16_t frag_id,
                    unsigned short seqNr,
                    bool isMark,
                    uint32_t timeStamp,
                    uint64_t send_ts_us);

    // Handle an ACK for a single fragment (frame_id, frag_id).
    // send_ts_us should be the original packet send timestamp echoed back by feedback.
    void handleAck(uint32_t frame_id, uint16_t frag_id, uint64_t send_ts_us);

    // Enable/disable encoder-side retransmissions
    void setRetransmitMode(bool enable);
    bool retransmitMode() const;

    // Packetize currently encoded frame into RTP packets and enqueue into rtp_queue_
    size_t packetize_encoded_frame(uint64_t frame_generation_ts,
                                   std::unique_ptr<ScreamV2Tx>* screamTx);

    // Access queue
    RtpQueue& rtpQueue() { return rtp_queue_; }

private:
    struct Impl;
    Impl* impl_;

    RtpQueue rtp_queue_;
    uint16_t next_seq_{0};

    struct SentPacket {
        void* pkt = nullptr;
        int size = 0;
        uint32_t frame_id = 0;
        uint16_t frag_id = 0;
        unsigned short seqNr = 0;
        bool isMark = false;
        uint32_t timeStamp = 0;

        uint64_t send_ts = 0;       // original send time
        uint64_t last_send_ts = 0;  // last send/retransmit time
        unsigned int num_rtx = 0;
    };

    // Key: (frame_id, frag_id)
    std::map<std::pair<uint32_t, uint16_t>, SentPacket> sent_packets_;
    std::mutex sent_packets_mutex_;

    bool retransmit_ = true;

    std::optional<unsigned int> min_rtt_us_{};
    std::optional<double> ewma_rtt_us_{};

    static constexpr double ALPHA = 0.2;
    static constexpr unsigned int MAX_NUM_RTX = 3;
    static constexpr uint64_t MAX_UNACKED_US = 1000 * 1000; // 1 second

    void addRttSample(unsigned int rtt_us);
};

#endif // SCREAM_ENCODER_H