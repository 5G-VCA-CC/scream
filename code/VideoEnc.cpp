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

// remove acknowledged packets from tracking and update RTT
void VideoEnc::acknowledge(unsigned int ackSeqNr, float currentTime) {
    auto it = unacked_.find(ackSeqNr);
    if (it == unacked_.end()) {
        // ACK for a packet we don't have tracked - could be very old
        return;
    }

    const UnackedPacket& pkt = it->second;
    
    // Calculate RTT sample from original send time
    float rttSample = currentTime - pkt.sendTimeUs;
    
    if (rttSample > 0.0f && rttSample < 10.0f) { // Sanity check: RTT should be 0-10 seconds
        // Update min RTT
        if (rttSample < minRttSec) {
            minRttSec = rttSample;
        }
        
        // Update EWMA RTT
        ewmaRttSec = EWMA_ALPHA * rttSample + (1.0f - EWMA_ALPHA) * ewmaRttSec;
    }
    
    // Remove the acknowledged packet
    unacked_.erase(it);
}

// Process ACK and determine if retransmissions are needed
int VideoEnc::processAck(unsigned int ackedSeqNr, float currentTime) {
    int numToRetransmit = 0;
    
    // Find the acked packet
    auto ackedIt = unacked_.find(ackedSeqNr);
    if (ackedIt == unacked_.end()) {
        return 0;  // ACK for unknown packet, ignore
    }
    
    // Retransmit all unacked packets BEFORE this one (backward iteration)
    // This follows the selective retransmission logic from ringmaster
    for (auto it = unacked_.begin(); it != ackedIt; ++it) {
        UnackedPacket& pkt = it->second;
        
        // Skip if already retransmitted too many times
        if (pkt.numRetx >= MAX_NUM_RTX) {
            std::cerr << "Encoder: Packet " << pkt.seqNr 
                      << " exceeded max retransmissions (" << MAX_NUM_RTX << ")" << std::endl;
            continue;
        }
        
        // Retransmit if first RTX or if sufficient time has passed (based on EWMA RTT)
        float timeSinceLastSend = currentTime - pkt.lastSendTimeUs;
        if (pkt.numRetx == 0 || timeSinceLastSend > ewmaRttSec) {
            pkt.numRetx++;
            pkt.lastSendTimeUs = currentTime;
            numToRetransmit++;
            
            std::cerr << "Encoder: Flagging retransmission for seqNr=" << pkt.seqNr 
                      << " (rtx count: " << pkt.numRetx << ")" << std::endl;
        }
    }
    
    // Process the ACK for the acked packet itself
    acknowledge(ackedSeqNr, currentTime);
    
    return numToRetransmit;
}

// Check if a specific packet should be retransmitted
bool VideoEnc::shouldRetransmit(unsigned int seqNr, float currentTime) {
    auto it = unacked_.find(seqNr);
    if (it == unacked_.end()) {
        return false;  // Already acked or unknown
    }
    
    const UnackedPacket& pkt = it->second;
    
    // Retransmit if:
    // 1. Not yet retransmitted (numRetx == 0)
    // 2. OR sufficient time has passed since last send
    float timeSinceLastSend = currentTime - pkt.lastSendTimeUs;
    bool shouldRtx = (pkt.numRetx == 0) || (timeSinceLastSend > ewmaRttSec);
    
    return shouldRtx && (pkt.numRetx < MAX_NUM_RTX);
}



int VideoEnc::encode(float time) {
    // Recovery logic: check if we need to force a keyframe due to unacked packets timeout
    if (!unacked_.empty()) {
        const UnackedPacket& firstUnacked = unacked_.begin()->second;
        float timeSinceFirstSend = time - firstUnacked.sendTimeUs;
        
        if (timeSinceFirstSend > MAX_UNACKED_TIME) {
            // We've given up on retransmitting old packets, force a keyframe to resync
            forceKeyFrame = true;
            recoveryMode = true;
            lastRecoveryTime = time;
            numKeyFramesForced++;
            
            std::cerr << "* Recovery: gave up retransmissions and forced a key frame at time " 
                      << time << "s (unacked for " << timeSinceFirstSend << "s)" << std::endl;
            std::cerr << "  - Oldest unacked packet: seqNr=" << firstUnacked.seqNr 
                      << ", retransmissions=" << firstUnacked.numRetx << std::endl;
            
            // Clear the unacked tracking and request RTP queue clear
            unacked_.clear();
            
            // Clear the RTP queue to start fresh after keyframe
            if (rtpQueue) {
                rtpQueue->clear();
                std::cout << "Encoder: Cleared RTP queue for recovery" << std::endl;
            }
        }
    }

    int rtpBytes = 0;
    char rtpPacket[2000];
    
    // Calculate base frame size from trace
    float baseSize = frameSize[ix];
    
    // Keyframe simulation: VP8E_SET_MAX_INTRA_BITRATE_PCT = 900 (9x-10x size)
    // This ensures keyframes are large enough to carry sufficient data
    if (forceKeyFrame) {
        baseSize = baseSize * 10.0f;
        forceKeyFrame = false;
        std::cerr << "Encoder: Generating forced keyframe with boosted size" << std::endl;
    }

    // Apply target bitrate scaling
    float tmp = (int)(baseSize / nominalBitrate * targetBitrate);

    // Apply sluggishness smoothing
    if (bytes > 0)
        bytes = bytes * (sluggishness) + (1.0 - sluggishness) * tmp;
    else
        bytes = tmp;

    int tmp2 = (int) bytes;

    ix++; 
    if (ix == nFrames) ix = 0;
    
    // Generate RTP packets for this frame
    while (tmp2 > 0) {
        int rtpSize = std::min(mss, tmp2);
        bool isMarker = rtpSize < mss;
        tmp2 -= rtpSize;
        rtpSize += kRtpOverHead;
        rtpBytes += rtpSize;
        
        // Push packet to RTP queue
        rtpQueue->push(rtpPacket, rtpSize, SSRC, seqNr, isMarker, time, timeStamp);
        
        // Track this packet as unacked
        UnackedPacket& unackedPkt = unacked_[seqNr];
        unackedPkt.seqNr = seqNr;
        unackedPkt.sendTimeUs = time;
        unackedPkt.lastSendTimeUs = time;
        unackedPkt.numRetx = 0;

        seqNr++;
        timeStamp = (unsigned long)(time * 90000);
    }
    
    rtpQueue->setSizeOfLastFrame(rtpBytes);
    return rtpBytes;
}