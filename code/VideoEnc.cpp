#include "VideoEnc.h"
#include <string.h>
#include <iostream>
#include <stdio.h>
#include <stdlib.h>
#include <algorithm>
#include <cmath>

using namespace std;

// Standard constants
static const int kRtpOverHead = 12 + 8; // RTP Header + UDP/IP overhead approx
static const int mss = 1200; // Maximum Segment Size
static const uint32_t SSRC = 100; // Fixed SSRC

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
    forceKeyFrame = false;

    FILE *fp = fopen(fname, "r");
    if (!fp) {
        cerr << "Error opening trace file: " << fname << endl;
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

// Ported: Handle ACKs to remove them from timeout tracking
void VideoEnc::acknowledge(uint16_t ackSeqNr) {
    auto it = unacked_packets.find(ackSeqNr);
    if (it != unacked_packets.end()) {
        unacked_packets.erase(it);
    }
}

int VideoEnc::encode(float time) {
    // --- Ported Logic: Check for Timeout ---
    if (!unacked_packets.empty()) {
        // Map is sorted by key (SeqNr), but we need sorted by Time. 
        // Assuming strictly increasing time, begin() is oldest unless wrap-around confusion occurs.
        // For simple simulation, begin() is roughly the oldest.
        float oldest_ts = unacked_packets.begin()->second;

        // Check if the oldest unacked packet has exceeded the timeout
        if (time - oldest_ts > MAX_UNACKED_TIME) {
            cerr << "[" << time << "] * Recovery: gave up retransmissions and forced a key frame. " 
                 << "Oldest unacked: " << (time - oldest_ts) << "s ago." << endl;

            // 1. Force next frame to be a Key Frame
            forceKeyFrame = true;

            // 2. Clear unacked list (stop waiting for old packets)
            unacked_packets.clear();

            // 3. Optional: Clear the RTP Queue to stop sending the stale data
            // (Assumes RtpQueue has a clear() method. If not, remove this line)
            if (rtpQueue) {
                rtpQueue->clear(); 
            }
        }
    }

    int rtpBytes = 0;
    char rtpPacket[2000]; // Dummy buffer for size simulation

    // Get base size from trace file
    float currentTraceSize = frameSize[ix];

    // Calculate target size based on bitrate scaling
    // (trace_size * target_bitrate / nominal_bitrate)
    float targetSize = currentTraceSize / nominalBitrate * targetBitrate;

    // --- Ported Logic: Force Keyframe Sizing ---
    if (forceKeyFrame) {
        // Simulating VP8E_SET_MAX_INTRA_BITRATE_PCT = 900
        // We override the smooth rate control and force a large frame immediately.
        bytes = targetSize * KEY_FRAME_MULTIPLIER;
        
        if (bytes < 1000) bytes = 1000; // Ensure it's at least some size
        
        forceKeyFrame = false; // Reset flag
        
        cout << "[" << time << "] Generating KeyFrame size: " << bytes << " bytes" << endl;
    } 
    else {
        // Standard SCReAM sluggishness (EWMA) to simulate rate control delay
        if (bytes > 0)
            bytes = bytes * sluggishness + targetSize * (1.0 - sluggishness);
        else
            bytes = targetSize;
    }

    // Packetize the frame
    int bytesToInt = (int)bytes;
    
    // Advance trace index
    ix++; 
    if (ix == nFrames) ix = 0;

    while (bytesToInt > 0) {
        int rtpSize = std::min(mss, bytesToInt);
        bool isMarker = (bytesToInt <= mss); // Last packet of frame gets Marker bit

        bytesToInt -= rtpSize;
        int fullPacketSize = rtpSize + kRtpOverHead;
        rtpBytes += fullPacketSize;

        // Push to transmission queue
        // Note: ringmaster used frame_id, SCReAM usually uses global time or frame count
        rtpQueue->push(rtpPacket, fullPacketSize, SSRC, seqNr, isMarker, time);

        // --- Ported Logic: Track Unacked Packets ---
        unacked_packets[seqNr] = time;

        seqNr++;
    }
    
    // Update RTP timestamp (90kHz clock)
    timeStamp += (uint32_t)(90000 / frameRate);

    // Tell queue about the frame boundary size for stats
    rtpQueue->setSizeOfLastFrame(rtpBytes);

    return rtpBytes;
}