#ifndef VIDEO_ENC_H
#define VIDEO_ENC_H

#include <map>
#include <optional>
#include <string>
#include <cstdint>
#include <fstream>

class RtpQueue;

#define MAX_FRAMES 10000

class VideoEnc {
public:
    VideoEnc(RtpQueue* rtpQueue_, float frameRate_, char *fname,
             int ixOffset_, float sluggishness_,
             bool retransmit = false,
             const std::string& outputPath = "");

    void setTargetBitrate(float targetBitrate_);
    int encode(float time);

    // ---- Ported from ringmaster::Encoder ----

    /// Full ACK handler: tracks RTT, triggers backward retransmission
    void handle_ack(unsigned int ackSeqNr, float ackSendTs, float currentTime);

    /// Simple ACK (original, still available as fallback)
    void acknowledge(unsigned int ackSeqNr);

    /// EWMA + min RTT tracking  (ringmaster::add_rtt_sample)
    void add_rtt_sample(float rtt_s);

    /// Periodic console stats        (ringmaster::output_periodic_stats)
    void output_periodic_stats();

    // Accessors
    std::optional<float> min_rtt()   const { return min_rtt_; }
    std::optional<float> ewma_rtt()  const { return ewma_rtt_; }
    size_t unacked_count()           const { return unacked_packets_.size(); }
    unsigned int frame_id()          const { return frame_id_; }
    void set_verbose(bool v) { verbose_ = v; }

private:
    RtpQueue* rtpQueue;
    float frameRate;
    float targetBitrate = 0.0f;
    float nominalBitrate;
    float sluggishness;
    float bytes;
    int ix;
    int nFrames;
    unsigned int seqNr;
    unsigned long timeStamp;
    float frameSize[MAX_FRAMES];
    bool forceKeyFrame = false;

    static constexpr int mss = 1200;
    static constexpr int kRtpOverHead = 12;
    static constexpr float MAX_UNACKED_TIME = 1.0f; // seconds

    // ---- Features ported from ringmaster ----

    static constexpr unsigned int MAX_NUM_RTX = 5;   // max retransmissions per pkt
    static constexpr float ALPHA = 0.1f;             // EWMA smoothing factor

    /// Mirrors ringmaster's per-datagram state kept in `unacked_`
    struct UnackedPacket {
        float send_ts      = 0.0f;   // first-send timestamp
        float last_send_ts = 0.0f;   // most-recent send timestamp
        unsigned int num_rtx = 0;    // retransmission count
        int   size         = 0;      // wire size (incl. RTP overhead)
        unsigned long rtp_ts = 0;    // RTP timestamp for retransmit

        UnackedPacket() = default;
        UnackedPacket(float ts, int sz, unsigned long rts)
            : send_ts(ts), last_send_ts(ts), num_rtx(0), size(sz), rtp_ts(rts) {}
    };

    /// ordered map so that iterators give sequence-number order
    std::map<unsigned int, UnackedPacket> unacked_packets_;

    // RTT tracking (ringmaster style)
    std::optional<float> min_rtt_;
    std::optional<float> ewma_rtt_;

    // Periodic-stats accumulators
    unsigned int num_encoded_frames_ = 0;
    float total_encode_time_  = 0.0f;
    float max_encode_time_    = 0.0f;

    // Controls
    bool retransmit_ = false;
    bool verbose_    = false;

    // Frame logging to file (like ringmaster's output_fd_)
    std::ofstream output_file_;
    unsigned int  frame_id_ = 0;
};

#endif