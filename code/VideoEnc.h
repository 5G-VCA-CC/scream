#ifndef VIDEO_ENC
#define VIDEO_ENC

#include <map> // Added for unacked tracking

static const int kRtpOverHead = 12;
class RtpQueue;

#define MAX_FRAMES 10000

class VideoEnc {
public:
    VideoEnc(RtpQueue* rtpQueue, float frameRate, char *fname, int ixOffset=0, float sluggishness = 0.0);

    int encode(float time);

    void setTargetBitrate(float targetBitrate);

    void setMss(int mss_) {
        mss = mss_;
    }

    // handle ACKs to track recovery timeout
    void acknowledge(unsigned int seqNr);

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

    // match ringmaster's recovery logic
    std::map<unsigned int, float> unacked_packets; // SeqNr -> SendTime
    static constexpr float MAX_UNACKED_TIME = 1.0f; // 1 second timeout
    bool forceKeyFrame = false;
};

#endif