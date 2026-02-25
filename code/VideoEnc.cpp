#include "VideoEnc.h"
#include "RtpQueue.h"
#include <string.h>
#include <iostream>
#include <stdio.h>
#include <stdlib.h>
#include <algorithm>

using namespace std;

uint32_t SSRC = 1;

VideoEnc::VideoEnc(RtpQueue* rtpQueue_, float frameRate_, char *fname, int ixOffset_, float sluggishness_) {
    rtpQueue = rtpQueue_;
    frameRate = frameRate_;
    ix = ixOffset_;
    nFrames = 0;
    seqNr = 0;
    timeStamp = 0;
    nominalBitrate = 0.0;
    sluggishness = sluggishness_;
    FILE *fp = fopen(fname,"r");
    char s[100];
    float sum = 0.0;
    bytes = 0.0f;
    while (fgets(s,99,fp)) {
        if (nFrames < MAX_FRAMES - 1) {
            float x = atof(s);
            frameSize[nFrames] = x;
            nFrames++;
            sum += x;
        }
    }
    float t = nFrames / frameRate;
    nominalBitrate = sum * 8 / t;
    fclose(fp);
}

void VideoEnc::setTargetBitrate(float targetBitrate_) {
    targetBitrate = targetBitrate_;
}

// remove acknowledged packets from tracking
void VideoEnc::acknowledge(unsigned int ackSeqNr) {
    auto it = unacked_packets.find(ackSeqNr);
    if (it != unacked_packets.end()) {
        unacked_packets.erase(it);
    }
}

int VideoEnc::encode(float time) {
    // if (us_since_first_send > MAX_UNACKED_US) -> Force Keyframe & Clear
    if (!unacked_packets.empty()) {
        float oldest_ts = unacked_packets.begin()->second;
        
        if (time - oldest_ts > MAX_UNACKED_TIME) {
            std::cerr << "* Recovery: gave up retransmissions and forced a key frame" << std::endl;
            forceKeyFrame = true;
            
            unacked_packets.clear();
        }
    }

    int rtpBytes = 0;
    char rtpPacket[2000];
    
    // Calculate base frame size from trace
    float baseSize = frameSize[ix];
    
    // keyframe simulation uses VP8E_SET_MAX_INTRA_BITRATE_PCT = 900 (9x-10x size)
    if (forceKeyFrame) {
        baseSize = baseSize * 10.0f; 
        forceKeyFrame = false;
    }

    float tmp = (int)(baseSize / nominalBitrate * targetBitrate);

    if (bytes > 0)
        bytes = bytes * (sluggishness)+(1.0 - sluggishness) * tmp;
    else
        bytes = tmp;

    int tmp2 = (int) bytes;

    ix++; if (ix == nFrames) ix = 0;
    
    while (tmp2 > 0) {
        int rtpSize = std::min(mss, tmp2);
        bool isMarker = rtpSize < mss;
        tmp2 -= rtpSize;
        rtpSize += kRtpOverHead;
        rtpBytes += rtpSize;
        
        rtpQueue->push(rtpPacket, rtpSize, SSRC, seqNr, isMarker, time, timeStamp);
        
        // track sent packets unacked_.emplace(...)
        unacked_packets[seqNr] = time;

        seqNr++;
        timeStamp = (unsigned long)(time * 90000);
    }
    rtpQueue->setSizeOfLastFrame(rtpBytes);
    return rtpBytes;
}