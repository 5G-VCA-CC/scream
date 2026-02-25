#include "VideoEnc.h"
#include <string.h>
#include <iostream>
#include <stdio.h>
#include <stdlib.h>
#include <algorithm>
#include <cmath>

using namespace std;

static const int kRtpOverHead = 12 + 8; // RTP Header + UDP/IP overhead
static const int mss = 1200; 
static const uint32_t SSRC = 100; // Fixed SSRC for simulation

VideoEnc::VideoEnc(RtpQueue* rtpQueue_, float frameRate_, char *fname, int ixOffset_, float sluggishness_) {
    rtpQueue = rtpQueue_;
    frameRate = frameRate_;
    ix = ixOffset_;
    nFrames = 0;
    seqNr = 0;
    timeStamp = 0;
    nominalBitrate = 0.0;
    sluggishness = sluggishness_;
    bytes = 0.0f;
    
    // Initialize Recovery State
    forceKeyFrame = false;

    FILE *fp = fopen(fname, "r");
    if (!fp) {
        cerr << "Error: Cannot open video trace file " << fname << endl;
        exit(1);
    }
    
    char s[100];
    float sum = 0.0;
    while (fgets(s, 99, fp)) {
        if (nFrames < MAX_FRAMES - 1) {
            float x = atof(s);
            frameSize[nFrames] = x;
            nFrames++;
            sum += x;
        }
    }
    fclose(fp);

    if (nFrames > 0) {
        float t = nFrames / frameRate;
        nominalBitrate = sum * 8 / t;
    }
}

void VideoEnc::setTargetBitrate(float targetBitrate_) {
    targetBitrate = targetBitrate_;
}

// -----------------------------------------------------------------------------
// Acknowledge:
// Removes the packet from the tracking map. This stops the timeout timer for it.
// -----------------------------------------------------------------------------
void VideoEnc::acknowledge(uint16_t ackSeqNr) {
    auto it = unacked_packets.find(ackSeqNr);
    if (it != unacked_packets.end()) {
        unacked_packets.erase(it);
    }
}

int VideoEnc::encode(float time) {
    // -------------------------------------------------------------------------
    // 1. Timeout / Recovery Logic
    // -------------------------------------------------------------------------
    if (!unacked_packets.empty()) {
        // Since map is sorted by seqNr, and seqNr increases with time,
        // begin() is roughly the oldest packet (ignoring wrap-around for now).
        float oldest_ts = unacked_packets.begin()->second;
        uint16_t oldest_seq = unacked_packets.begin()->first;

        if (time - oldest_ts > MAX_UNACKED_TIME) {
            std::cout << "[" << time << "] VideoEnc Recovery: Packet " << oldest_seq 
                      << " timed out (" << (time - oldest_ts)*1000 << "ms). "
                      << "Clearing Queue & Forcing KeyFrame." << std::endl;

            // A. Force the NEXT frame to be a Keyframe (I-Frame)
            forceKeyFrame = true;

            // B. Give up on all currently unacked packets
            unacked_packets.clear();

            // C. CRITICAL: Clear the RTP Transmission Queue.
            // We are dropping the "stuck" delta frames so the Keyframe can go out immediately.
            if (rtpQueue) {
                rtpQueue->clear();
            }
        }
    }

    // -------------------------------------------------------------------------
    // 2. Determine Frame Size
    // -------------------------------------------------------------------------
    int rtpBytes = 0;
    char rtpPacket[2000]; // Dummy buffer
    
    // Get base size from trace file
    float traceVal = frameSize[ix];
    
    // Scale based on Congestion Control target
    float targetSize = traceVal * (targetBitrate / nominalBitrate);

    bool isKeyFrameCurrent = false;

    if (forceKeyFrame) {
        // Simulate a Keyframe size (large spike, typically 10x a P-frame)
        bytes = targetSize * KEY_FRAME_MULTIPLIER;
        
        // Ensure a minimum size for I-frames
        if (bytes < 2000) bytes = 2000;

        isKeyFrameCurrent = true;
        forceKeyFrame = false; // Reset flag
        
        // Debug output
        // cout << "Encoding KeyFrame size: " << bytes << endl;
    } 
    else {
        // Standard "Sluggish" rate control (EWMA) for P-frames
        if (bytes > 0)
            bytes = bytes * sluggishness + targetSize * (1.0 - sluggishness);
        else
            bytes = targetSize;
    }

    int bytesToInt = (int)bytes;
    
    // Advance trace index
    ix++; 
    if (ix == nFrames) ix = 0;

    // -------------------------------------------------------------------------
    // 3. Packetize and Push to Queue
    // -------------------------------------------------------------------------
    while (bytesToInt > 0) {
        int rtpSize = std::min(mss, bytesToInt);
        bool isMarker = (bytesToInt <= mss); // Last packet of the frame
        
        bytesToInt -= rtpSize;
        int fullPacketSize = rtpSize + kRtpOverHead;
        rtpBytes += fullPacketSize;

        // Push to RTP Queue
        // NOTE: We pass 'isKeyFrameCurrent' so the Receiver knows to reset OOO counters
        rtpQueue->push(rtpPacket, fullPacketSize, SSRC, seqNr, isMarker, time, isKeyFrameCurrent);

        // Track this packet for timeouts
        unacked_packets[seqNr] = time;

        seqNr++;
    }

    // Update RTP timestamp (90kHz clock)
    timeStamp += (uint32_t)(90000 / frameRate);
    
    // Notify queue about the frame boundary for stats
    rtpQueue->setSizeOfLastFrame(rtpBytes);

    return rtpBytes;
}