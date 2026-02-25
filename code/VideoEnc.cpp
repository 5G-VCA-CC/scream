#include "VideoEnc.h"
#include "RtpQueue.h"

#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <algorithm>
#include <chrono>
#include <iterator>   // std::make_reverse_iterator

using namespace std;

static uint32_t SSRC = 1;

// ---------------------------------------------------------------------------
// Constructor – now accepts retransmit flag and optional log-file path
// ---------------------------------------------------------------------------
VideoEnc::VideoEnc(RtpQueue* rtpQueue_,
                   float frameRate_,
                   char *fname,
                   int ixOffset_,
                   float sluggishness_,
                   bool retransmit,
                   const string& outputPath)
    : rtpQueue(rtpQueue_),
      frameRate(frameRate_),
      ix(ixOffset_),
      nFrames(0),
      seqNr(0),
      timeStamp(0),
      nominalBitrate(0.0f),
      sluggishness(sluggishness_),
      bytes(0.0f),
      retransmit_(retransmit)
{
    // ---- read frame-size trace (original) ----
    FILE *fp = fopen(fname, "r");
    if (!fp) {
        cerr << "VideoEnc: cannot open trace file " << fname << endl;
        exit(1);
    }
    char s[100];
    float sum = 0.0f;
    while (fgets(s, 99, fp)) {
        if (nFrames < MAX_FRAMES - 1) {
            float x = atof(s);
            frameSize[nFrames] = x;
            nFrames++;
            sum += x;
        }
    }
    fclose(fp);
    float t = nFrames / frameRate;
    nominalBitrate = sum * 8.0f / t;

    // ---- open output log file (from ringmaster) ----
    if (!outputPath.empty()) {
        output_file_.open(outputPath, ios::out | ios::trunc);
        if (output_file_.is_open()) {
            output_file_ << "frame_id,target_bitrate,frame_size,encode_time\n";
        }
    }
}

// ---------------------------------------------------------------------------
void VideoEnc::setTargetBitrate(float targetBitrate_) {
    targetBitrate = targetBitrate_;
}

// ---------------------------------------------------------------------------
// RTT tracking  (ported from ringmaster::Encoder::add_rtt_sample)
// ---------------------------------------------------------------------------
void VideoEnc::add_rtt_sample(float rtt_s)
{
    // min RTT
    if (!min_rtt_ || rtt_s < *min_rtt_) {
        min_rtt_ = rtt_s;
    }

    // EWMA RTT
    if (!ewma_rtt_) {
        ewma_rtt_ = rtt_s;
    } else {
        ewma_rtt_ = ALPHA * rtt_s + (1.0f - ALPHA) * (*ewma_rtt_);
    }
}

// ---------------------------------------------------------------------------
// Full ACK handler  (ported from ringmaster::Encoder::handle_ack)
//
//  • Records an RTT sample from the ACK.
//  • Finds the ACKed packet in `unacked_packets_`.
//  • Walks *backward* from the ACKed packet and retransmits every earlier
//    unacked packet that (a) has not exceeded MAX_NUM_RTX and (b) was last
//    sent at least one EWMA-RTT ago.
//  • Erases the ACKed packet.
// ---------------------------------------------------------------------------
void VideoEnc::handle_ack(unsigned int ackSeqNr,
                          float        ackSendTs,
                          float        currentTime)
{
    // --- RTT sample ---
    float rtt = currentTime - ackSendTs;
    add_rtt_sample(rtt);

    // --- locate the ACKed packet ---
    auto acked_it = unacked_packets_.find(ackSeqNr);
    if (acked_it == unacked_packets_.end()) {
        return;   // ACK for an unknown / already-acked packet
    }

    // --- backward retransmission (ringmaster logic) ---
    if (retransmit_) {
        for (auto rit = make_reverse_iterator(acked_it);
             rit != unacked_packets_.rend(); ++rit)
        {
            auto& pkt = rit->second;

            // skip if retransmission budget exhausted
            if (pkt.num_rtx >= MAX_NUM_RTX) {
                continue;
            }

            // retransmit on first RTX, or if last send was ≥ 1 EWMA-RTT ago
            if (pkt.num_rtx == 0 ||
                (ewma_rtt_ && (currentTime - pkt.last_send_ts > *ewma_rtt_)))
            {
                pkt.num_rtx++;
                pkt.last_send_ts = currentTime;

                // push retransmission into the RTP queue
                char rtpPacket[2000] = {};
                rtpQueue->push(rtpPacket, pkt.size, SSRC,
                               rit->first,        // original seqNr
                               false,              // not marker (best-effort)
                               currentTime,
                               pkt.rtp_ts);

                if (verbose_) {
                    cerr << "  RTX seqNr=" << rit->first
                         << " rtx#=" << pkt.num_rtx << endl;
                }
            }
        }
    }

    // --- erase the ACKed packet ---
    unacked_packets_.erase(acked_it);
}

// ---------------------------------------------------------------------------
// Simple acknowledge (original, kept for backward compatibility)
// ---------------------------------------------------------------------------
void VideoEnc::acknowledge(unsigned int ackSeqNr)
{
    unacked_packets_.erase(ackSeqNr);
}

// ---------------------------------------------------------------------------
// Periodic stats  (ported from ringmaster::Encoder::output_periodic_stats)
// ---------------------------------------------------------------------------
void VideoEnc::output_periodic_stats()
{
    cerr << "Frames encoded in the last period: " << num_encoded_frames_ << endl;

    if (num_encoded_frames_ > 0) {
        cerr << "  - Avg/Max encode time (ms): "
             << (total_encode_time_ / num_encoded_frames_ * 1000.0f)
             << " / " << (max_encode_time_ * 1000.0f) << endl;
    }

    if (min_rtt_ && ewma_rtt_) {
        cerr << "  - Min/EWMA RTT (ms): "
             << (*min_rtt_  * 1000.0f) << " / "
             << (*ewma_rtt_ * 1000.0f) << endl;
    }

    cerr << "  - Unacked packets: " << unacked_packets_.size() << endl;

    // reset accumulators (keep RTT state)
    num_encoded_frames_  = 0;
    total_encode_time_   = 0.0f;
    max_encode_time_     = 0.0f;
}

// ---------------------------------------------------------------------------
// encode()  – original logic + ringmaster enhancements
// ---------------------------------------------------------------------------
int VideoEnc::encode(float time)
{
    // ------------------------------------------------------------------
    // 1. Key-frame recovery  (from ringmaster: MAX_UNACKED_US check)
    //    If the oldest unacked packet has been pending > MAX_UNACKED_TIME,
    //    give up on retransmissions and force a key frame.
    // ------------------------------------------------------------------
    if (!unacked_packets_.empty()) {
        const auto& oldest = unacked_packets_.begin()->second;
        float age = time - oldest.send_ts;

        if (age > MAX_UNACKED_TIME) {
            cerr << "* Recovery: gave up retransmissions and forced a key frame "
                 << frame_id_ << endl;

            if (verbose_) {
                cerr << "  oldest seqNr=" << unacked_packets_.begin()->first
                     << " age=" << age << "s" << endl;
            }

            forceKeyFrame = true;

            // clean up  (ringmaster clears both queue and unacked map)
            unacked_packets_.clear();
            // Note: if RtpQueue exposes a clear(), call it here:
            // rtpQueue->clear();
        }
    }

    // ------------------------------------------------------------------
    // 2. Compute encoded frame size from trace + target bitrate
    // ------------------------------------------------------------------
    auto enc_start = chrono::steady_clock::now();

    float baseSize = frameSize[ix];

    // key-frame inflation (VP8E_SET_MAX_INTRA_BITRATE_PCT = 900 ⇒ ~10×)
    if (forceKeyFrame) {
        baseSize *= 10.0f;
        forceKeyFrame = false;
        if (verbose_) {
            cerr << "Encoded a key frame: frame_id=" << frame_id_ << endl;
        }
    }

    float tmp = static_cast<float>(
        static_cast<int>(baseSize / nominalBitrate * targetBitrate));

    if (bytes > 0)
        bytes = bytes * sluggishness + (1.0f - sluggishness) * tmp;
    else
        bytes = tmp;

    int remaining = static_cast<int>(bytes);

    ix++;
    if (ix == nFrames) ix = 0;

    // ------------------------------------------------------------------
    // 3. Packetize into RTP packets
    //    (marker-bit fix: set when remaining bytes will be consumed)
    // ------------------------------------------------------------------
    int rtpBytes = 0;
    char rtpPacket[2000] = {};

    // Set RTP timestamp *before* the loop (ringmaster sets frame_generation_ts
    // at the top of compress_frame, not after packetization)
    timeStamp = static_cast<unsigned long>(time * 90000);

    while (remaining > 0) {
        int payloadSize = min(mss, remaining);
        remaining -= payloadSize;

        // marker bit: true for the *last* fragment of the frame
        bool isMarker = (remaining <= 0);

        int rtpSize = payloadSize + kRtpOverHead;
        rtpBytes += rtpSize;

        rtpQueue->push(rtpPacket, rtpSize, SSRC, seqNr,
                       isMarker, time, timeStamp);

        // --- track in unacked map (enhanced, from ringmaster) ---
        unacked_packets_[seqNr] = UnackedPacket(time, rtpSize, timeStamp);

        seqNr++;
    }

    rtpQueue->setSizeOfLastFrame(rtpBytes);

    // ------------------------------------------------------------------
    // 4. Encoding-time stats  (from ringmaster)
    // ------------------------------------------------------------------
    auto enc_end = chrono::steady_clock::now();
    float enc_time_s = chrono::duration<float>(enc_end - enc_start).count();

    num_encoded_frames_++;
    total_encode_time_ += enc_time_s;
    max_encode_time_    = max(max_encode_time_, enc_time_s);

    // ------------------------------------------------------------------
    // 5. Frame logging to file  (from ringmaster's output_fd_ writes)
    // ------------------------------------------------------------------
    if (output_file_.is_open()) {
        output_file_ << frame_id_ << ","
                     << targetBitrate << ","
                     << rtpBytes << ","
                     << enc_time_s << "\n";
    }

    frame_id_++;
    return rtpBytes;
}