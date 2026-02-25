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

    // handle ACKs to track recovery timeout
    void acknowledge(u_int16_t seqNr);

    float getNominalBitrate(){return nominalBitrate;}

    private:
        RtpQueue* rtpQueue;
        float frameRate;
        float nominalBitrate;
        float targetBitrate;
        float sluggishness;
        float bytes; // Running average of frame size
        
        // Trace file data
        float frameSize[MAX_FRAMES];
        int nFrames;
        int ix; // Current frame index

        // RTP / Sequence state
        uint16_t seqNr;
        uint32_t timeStamp;

        // --- Ported from Ringmaster Encoder ---
        
        // Map of SeqNr -> Send Time (seconds)
        std::map<uint16_t, float> unacked_packets;
        
        bool forceKeyFrame = false;

        // Timeout threshold (e.g., 0.5 seconds / 500ms)
        const float MAX_UNACKED_TIME = 0.5f; 
        
        // Multiplier to simulate I-Frame size (Ringmaster uses 900% cap, we use 10x)
        const float KEY_FRAME_MULTIPLIER = 10.0f;
};

#endif