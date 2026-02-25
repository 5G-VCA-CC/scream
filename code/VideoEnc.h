#ifndef VIDEO_ENC_H
#define VIDEO_ENC_H

#include "RtpQueue.h"
#include <stdio.h>
#include <map>
#include <cstdint>

#define MAX_FRAMES 10000

class VideoEnc {
public:
    VideoEnc(RtpQueue* rtpQueue, float frameRate, char *fname, int ixOffset = 0, float sluggishness = 0.0);

    // Call this when the sender receives an ACK for a specific sequence number
    void acknowledge(uint16_t seqNr);

    void setTargetBitrate(float targetBitrate);
    int encode(float time);

    // Getters for stats if needed
    float getNominalBitrate() { return nominalBitrate; }

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
    
    // --------------------------------------
};

#endif