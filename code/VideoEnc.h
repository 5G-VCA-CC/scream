#ifndef VIDEO_ENC
#define VIDEO_ENC

#include <map>
#include <cstdint>

static const int kRtpOverHead = 12;
class RtpQueue;

#define MAX_FRAMES 10000
#define MAX_NUM_RTX 3        // Max retransmissions per packet
#define MAX_UNACKED_US 1000000.0f // 1 second timeout in microseconds

class VideoEnc {
public:
    VideoEnc(RtpQueue* rtpQueue, float frameRate, char *fname, int ixOffset=0, float sluggishness = 0.0);

    int encode(float time);

    void setTargetBitrate(float targetBitrate);

    void setMss(int mss_) {
        mss = mss_;
    }

    // Handle ACKs to track recovery timeout and trigger retransmissions
    void acknowledge(unsigned int seqNr, float currentTime);
    
    // Process ACK and determine if retransmissions are needed
    // Returns the number of packets to retransmit
    int processAck(unsigned int ackedSeqNr, float currentTime);
    
    // Check if a specific packet should be retransmitted
    bool shouldRetransmit(unsigned int seqNr, float currentTime);

    RtpQueue* rtpQueue;
    float frameSize[MAX_FRAMES];
    int nFrames;
    float targetBitrate;
    float frameRate;
    float nominalBitrate;
    unsigned int seqNr;
    unsigned long timeStamp;
    int ix;
    int mss;

    float sluggishness;
    float bytes;

    // Enhanced unacked packet tracking (similar to ringmaster)
    struct UnackedPacket {
        uint16_t seqNr;
        uint8_t* data;        // pointer to packet buffer (owned by RtpQueue until pop)
        int size;
        uint32_t ts;
        bool isMark;
        uint64_t sendTimeUs;     // initial send time (microseconds)
        uint64_t lastSendTimeUs; // last retransmit time (microseconds)
        int numRetx;
    };

    std::map<unsigned int, UnackedPacket> unacked_;  // SeqNr -> UnackedPacket info
    
    // Recovery timeout parameters
    static constexpr float MAX_UNACKED_TIME = 1.0f;  // 1 second timeout
    static constexpr float EWMA_ALPHA = 0.125f;      // EWMA smoothing factor for RTT
    
    // RTT tracking
    float minRttSec = 10.0f;
    float ewmaRttSec = 0.05f;  // Initial estimate: 50ms
    
    // Recovery state
    bool forceKeyFrame = false;
    bool recoveryMode = false;
    float lastRecoveryTime = -1.0f;

    // Stats
    int numRetransmissions = 0;
    int numKeyFramesForced = 0;
};

#endif