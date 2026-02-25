#ifndef VIDEO_ENC_H
#define VIDEO_ENC_H

#include "RtpQueue.h"
#include <stdio.h>
#include <map>
#include <vector>

#define MAX_FRAMES 10000

class VideoEnc {
public:
    VideoEnc(RtpQueue* rtpQueue, float frameRate, char *fname, int ixOffset = 0, float sluggishness = 0.0);

    // Call this when an ACK is received from the network
    void acknowledge(uint16_t seqNr);

    void setTargetBitrate(float targetBitrate);
    
    // Returns number of bytes generated
    int encode(float time);

    float getNominalBitrate() { return nominalBitrate; }

private:
    RtpQueue* rtpQueue;
    float frameRate;
    float nominalBitrate;
    float targetBitrate;
    float sluggishness;
    float bytes; // Running average of frame size
    
    float frameSize[MAX_FRAMES];
    int nFrames;
    int ix;
    uint16_t seqNr;
    uint32_t timeStamp;

    // --- Ringmaster / Recovery Logic ---
    
    // Map of SequenceNumber -> SendTime (seconds)
    // Used to track how long a packet has been "in flight" without ACK
    std::map<uint16_t, float> unacked_packets;
    
    bool forceKeyFrame;

    // Time (seconds) before giving up on a packet and forcing a resync.
    // 0.2s (200ms) is typical for low-latency interactive video.
    const float MAX_UNACKED_TIME = 0.2f; 
    
    // Keyframes are significantly larger than delta frames (approx 10x)
    const float KEY_FRAME_MULTIPLIER = 10.0f;
};

#endif