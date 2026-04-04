#include "Encoder.h"

#include <vpx/vpx_encoder.h>
#include <vpx/vp8cx.h>

#include <memory>
#include <cstring>
#include <stdexcept>
#include <limits>
#include <sys/time.h>
#include <arpa/inet.h>
#include <iostream>
#include <pthread.h>
#include <iterator>

#include "ScreamTx.h"

struct Encoder::Impl {
    vpx_codec_ctx_t ctx{};
    vpx_codec_enc_cfg_t cfg{};
    int width;
    int height;
    int framerate;
    unsigned int bitrate_kbps;
    uint64_t frame_id = 0;

    // Periodic key frame control
    bool use_periodic_keyframes = false;
    uint64_t keyframe_interval_us = 2000000; // default 2 seconds
    uint64_t last_keyframe_ts_us = 0;

    // Feedback-timeout key frame control
    bool use_feedback_timeout_keyframes = false;
    uint64_t max_unacked_us = 1000000; // default 1s
    bool has_triggered = false;
    uint16_t last_triggered_seq = 0;

    // One-shot forced key frame
    bool force_keyframe = false;

    // Optional feedback timestamp tracking
    uint64_t last_feedback_ts_us = 0;
    bool feedback_ever_received = false;

    // ScreamV2Tx object to access txPackets data
    ScreamV2Tx* screamTx;
    pthread_mutex_t* lock_scream;
    uint32_t ssrc;
};

// Helper to get current timestamp in microseconds
static uint64_t get_timestamp_us() {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (uint64_t)tv.tv_sec * 1000000 + tv.tv_usec;
}

static void writeRtpHeader(uint8_t* buf,
                           unsigned short seqNr,
                           uint32_t timeStamp,
                           uint32_t ssrc,
                           uint8_t pt = 98) {
    seqNr = htons(seqNr);
    timeStamp = htonl(timeStamp);
    uint32_t ssrc_n = htonl(ssrc);

    buf[0] = 0x80;
    buf[1] = pt;
    memcpy(buf + 2, &seqNr, 2);
    memcpy(buf + 4, &timeStamp, 4);
    memcpy(buf + 8, &ssrc_n, 4);
}

static constexpr size_t kRtpHeaderSize = 12;

Encoder::Encoder(int width,
                 int height,
                 int framerate,
                 unsigned int bitrate_kbps,
                 ScreamV2Tx* screamTx,
                 pthread_mutex_t* lock_scream,
                 uint32_t ssrc)
    : impl_(new Impl()) {
    impl_->width = width;
    impl_->height = height;
    impl_->framerate = framerate;
    impl_->bitrate_kbps = bitrate_kbps;
    impl_->screamTx = screamTx;
    impl_->lock_scream = lock_scream;
    impl_->ssrc = ssrc;

    if (vpx_codec_enc_config_default(&vpx_codec_vp9_cx_algo, &impl_->cfg, 0) != VPX_CODEC_OK) {
        throw std::runtime_error("vpx_codec_enc_config_default failed");
    }

    impl_->cfg.g_w = width;
    impl_->cfg.g_h = height;
    impl_->cfg.g_timebase.num = 1;
    impl_->cfg.g_timebase.den = framerate > 0 ? framerate : 25;
    impl_->cfg.g_pass = VPX_RC_ONE_PASS;
    impl_->cfg.g_lag_in_frames = 0;
    impl_->cfg.g_error_resilient = VPX_ERROR_RESILIENT_DEFAULT;
    impl_->cfg.g_threads = 4;
    impl_->cfg.rc_resize_allowed = 0;
    impl_->cfg.rc_dropframe_thresh = 0;

    // Buffering / RC parameters
    impl_->cfg.rc_buf_initial_sz = 500;
    impl_->cfg.rc_buf_optimal_sz = 600;
    impl_->cfg.rc_buf_sz = 1000;

    impl_->cfg.rc_min_quantizer = 2;
    impl_->cfg.rc_max_quantizer = 52;
    impl_->cfg.rc_undershoot_pct = 50;
    impl_->cfg.rc_overshoot_pct = 50;

    // Prevent automatic key frames
    impl_->cfg.kf_mode = VPX_KF_DISABLED;
    impl_->cfg.kf_max_dist = std::numeric_limits<unsigned int>::max();
    impl_->cfg.kf_min_dist = 0;

    impl_->cfg.rc_end_usage = VPX_CBR;
    impl_->cfg.rc_target_bitrate = bitrate_kbps;

    if (vpx_codec_enc_init(&impl_->ctx, &vpx_codec_vp9_cx_algo, &impl_->cfg, 0) != VPX_CODEC_OK) {
        throw std::runtime_error("vpx_codec_enc_init failed");
    }

    // realtime settings
    vpx_codec_control(&impl_->ctx, VP8E_SET_CPUUSED, 12);
    vpx_codec_control(&impl_->ctx, VP9E_SET_TILE_COLUMNS, 2);
    vpx_codec_control(&impl_->ctx, VP9E_SET_ROW_MT, 1);

    vpx_codec_control(&impl_->ctx, VP8E_SET_MAX_INTRA_BITRATE_PCT, 900);
    vpx_codec_control(&impl_->ctx, VP8E_SET_STATIC_THRESHOLD, 1);
    vpx_codec_control(&impl_->ctx, VP9E_SET_AQ_MODE, 3);
    vpx_codec_control(&impl_->ctx, VP9E_SET_NOISE_SENSITIVITY, 1);
    vpx_codec_control(&impl_->ctx, VP9E_SET_FRAME_PARALLEL_DECODING, 0);

    std::cerr << "Initialized VP9 encoder" << std::endl;
}

Encoder::~Encoder() {
    if (impl_) {
        vpx_codec_destroy(&impl_->ctx);
        delete impl_;
        impl_ = nullptr;
    }
}

void Encoder::setBitrate(unsigned int bitrate_kbps) {
    if (!impl_) return;
    if (bitrate_kbps == impl_->bitrate_kbps) return;

    impl_->bitrate_kbps = bitrate_kbps;
    impl_->cfg.rc_target_bitrate = bitrate_kbps;
    vpx_codec_enc_config_set(&impl_->ctx, &impl_->cfg);
}

void Encoder::setPeriodicKeyframes(bool enable, uint64_t interval_us) {
    if (!impl_) return;
    impl_->use_periodic_keyframes = enable;
    impl_->keyframe_interval_us = interval_us;
}

void Encoder::setFeedbackTimeoutKeyframes(bool enable, uint64_t timeout_us) {
    if (!impl_) return;
    impl_->use_feedback_timeout_keyframes = enable;
    impl_->max_unacked_us = timeout_us;
}

void Encoder::notifyFeedbackReceived() {
    if (!impl_) return;
    impl_->last_feedback_ts_us = get_timestamp_us();
    impl_->feedback_ever_received = true;
}

void Encoder::forceNextKeyframe() {
    if (!impl_) return;
    impl_->force_keyframe = true;
}

void Encoder::setRetransmitMode(bool enable) {
    retransmit_ = enable;
}

bool Encoder::retransmitMode() const {
    return retransmit_;
}

void Encoder::addRttSample(unsigned int rtt_us) {
    if (!min_rtt_us_ || rtt_us < *min_rtt_us_) {
        min_rtt_us_ = rtt_us;
    }

    if (!ewma_rtt_us_) {
        ewma_rtt_us_ = rtt_us;
    } else {
        ewma_rtt_us_ = ALPHA * rtt_us + (1.0 - ALPHA) * (*ewma_rtt_us_);
    }
}

void Encoder::addUnacked(void* pkt,
                         int size,
                         uint32_t frame_id,
                         uint16_t frag_id,
                         unsigned short seqNr,
                         bool isMark,
                         uint32_t timeStamp,
                         uint64_t send_ts_us) {
    std::lock_guard<std::mutex> lock(sent_packets_mutex_);

    SentPacket sp;
    sp.pkt = pkt;
    sp.size = size;
    sp.frame_id = frame_id;
    sp.frag_id = frag_id;
    sp.seqNr = seqNr;
    sp.isMark = isMark;
    sp.timeStamp = timeStamp;
    sp.send_ts = send_ts_us;
    sp.last_send_ts = send_ts_us;
    sp.num_rtx = 0;

    auto key = std::make_pair(frame_id, frag_id);
    auto [it, inserted] = sent_packets_.emplace(key, sp);
    if (!inserted) {
        throw std::runtime_error("sent packet already exists in sent_packets_");
    }
}

void Encoder::handleAck(uint32_t frame_id, uint16_t frag_id, uint64_t send_ts_us) {
    const uint64_t curr_ts = get_timestamp_us();

    if (curr_ts >= send_ts_us) {
        addRttSample(static_cast<unsigned int>(curr_ts - send_ts_us));
    }

    std::lock_guard<std::mutex> lock(sent_packets_mutex_);

    auto acked_key = std::make_pair(frame_id, frag_id);
    auto acked_it = sent_packets_.find(acked_key);

    if (acked_it == sent_packets_.end()) {
        // ACK for packet no longer tracked
        return;
    }

    if (retransmit_) {
        // retransmit all older unacked packets before the acked one
        for (auto rit = std::make_reverse_iterator(acked_it);
             rit != sent_packets_.rend(); ++rit) {
            SentPacket &pkt = rit->second;

            if (pkt.num_rtx >= MAX_NUM_RTX) {
                continue;
            }

            bool should_rtx = false;

            if (pkt.num_rtx == 0) {
                should_rtx = true;
            } else if (ewma_rtt_us_ &&
                       (curr_ts - pkt.last_send_ts > static_cast<uint64_t>(*ewma_rtt_us_))) {
                should_rtx = true;
            }

            if (should_rtx) {
                pkt.num_rtx++;
                pkt.last_send_ts = curr_ts;

                std::cerr << "Encoder: Retransmitting frame=" << pkt.frame_id
                          << " frag=" << pkt.frag_id
                          << " seq=" << pkt.seqNr
                          << " rtx=" << pkt.num_rtx << std::endl;

                bool ok = rtp_queue_.push_front(pkt.pkt,
                                                pkt.size,
                                                impl_->ssrc,
                                                pkt.seqNr,
                                                pkt.isMark,
                                                curr_ts / 1e6f,
                                                pkt.timeStamp);

                if (!ok) {
                    std::cerr << "Encoder: failed to enqueue retransmission (queue full)" << std::endl;
                }
            }
        }
    }

    // Finally remove the ACKed packet
    sent_packets_.erase(acked_it);
}

std::vector<uint8_t> Encoder::encodeFrame(const std::vector<uint8_t> &yuv_frame) {
    if (!impl_) return {};

    const int w = impl_->width;
    const int h = impl_->height;
    const size_t y_size = (size_t)w * h;
    const size_t uv_size = y_size / 4;

    if (yuv_frame.size() < y_size + 2 * uv_size) {
        throw std::runtime_error("yuv frame too small");
    }

    vpx_image_t *img = vpx_img_alloc(NULL, VPX_IMG_FMT_I420, w, h, 1);
    if (!img) {
        throw std::runtime_error("vpx_img_alloc failed");
    }

    memcpy(img->planes[VPX_PLANE_Y], yuv_frame.data(), y_size);
    memcpy(img->planes[VPX_PLANE_U], yuv_frame.data() + y_size, uv_size);
    memcpy(img->planes[VPX_PLANE_V], yuv_frame.data() + y_size + uv_size, uv_size);

    vpx_enc_frame_flags_t flags = 0;
    const uint64_t curr_ts = get_timestamp_us();

    // 1) One-shot forced keyframe
    if (impl_->force_keyframe) {
        flags = VPX_EFLAG_FORCE_KF;
        impl_->force_keyframe = false;
        impl_->last_keyframe_ts_us = curr_ts;

        std::cerr << "* Loss-triggered key frame forced at frame "
                  << impl_->frame_id << std::endl;
    }
    else {
        // 2) Recovery if oldest locally tracked unacked packet is too old
        {
            std::lock_guard<std::mutex> lock(sent_packets_mutex_);
            if (!sent_packets_.empty()) {
                const auto &first_unacked = sent_packets_.begin()->second;
                const uint64_t us_since_first_send = curr_ts - first_unacked.send_ts;

                if (us_since_first_send > MAX_UNACKED_US) {
                    flags = VPX_EFLAG_FORCE_KF;
                    impl_->last_keyframe_ts_us = curr_ts;

                    std::cerr << "* Recovery: gave up retransmissions and forced a key frame at frame "
                              << impl_->frame_id << std::endl;

                    rtp_queue_.clear();
                    sent_packets_.clear();
                }
            }
        }

        // 3) Periodic key frame timer
        if (flags == 0 && impl_->use_periodic_keyframes) {
            if (impl_->last_keyframe_ts_us == 0 ||
                curr_ts - impl_->last_keyframe_ts_us >= impl_->keyframe_interval_us) {
                flags = VPX_EFLAG_FORCE_KF;
                impl_->last_keyframe_ts_us = curr_ts;

                std::cerr << "* Periodic key frame forced at frame "
                          << impl_->frame_id
                          << " (interval: "
                          << impl_->keyframe_interval_us / 1000
                          << " ms)" << std::endl;
            }
        }

        // 4) Existing SCReAM-based feedback timeout trigger
        if (flags == 0 && impl_->use_feedback_timeout_keyframes && impl_->screamTx) {
            uint16_t oldest_unacked_seq = 0;
            uint32_t oldest_unacked_ts = 0;

            pthread_mutex_lock(impl_->lock_scream);
            bool has_oldest = impl_->screamTx->getOldestUnacked(impl_->ssrc,
                                                                oldest_unacked_seq,
                                                                oldest_unacked_ts);
            pthread_mutex_unlock(impl_->lock_scream);

            if (has_oldest) {
                uint64_t us_since_first_send = curr_ts - oldest_unacked_ts;
                if (us_since_first_send > impl_->max_unacked_us) {
                    if (impl_->last_triggered_seq != oldest_unacked_seq) {
                        flags = VPX_EFLAG_FORCE_KF;
                        impl_->last_triggered_seq = oldest_unacked_seq;
                        impl_->last_keyframe_ts_us = curr_ts;

                        std::cerr << "* SCReAM feedback-timeout key frame forced at frame "
                                  << impl_->frame_id
                                  << " oldest_seq=" << oldest_unacked_seq
                                  << std::endl;
                    }
                }
            }
        }
    }

    if (vpx_codec_encode(&impl_->ctx,
                         img,
                         impl_->frame_id++,
                         1,
                         flags,
                         VPX_DL_REALTIME) != VPX_CODEC_OK) {
        vpx_img_free(img);
        throw std::runtime_error("vpx_codec_encode failed");
    }

    std::vector<uint8_t> out;
    vpx_codec_iter_t iter = NULL;
    const vpx_codec_cx_pkt_t *pkt;

    while ((pkt = vpx_codec_get_cx_data(&impl_->ctx, &iter))) {
        if (pkt->kind == VPX_CODEC_CX_FRAME_PKT) {
            const uint8_t* b = reinterpret_cast<const uint8_t*>(pkt->data.frame.buf);
            out.insert(out.end(), b, b + pkt->data.frame.sz);
        }
    }

    vpx_img_free(img);
    return out;
}

size_t Encoder::packetize_encoded_frame(uint64_t frame_generation_ts,
                                        std::unique_ptr<ScreamV2Tx>* screamTx) {
    if (!impl_) return 0;

    const vpx_codec_cx_pkt_t *encoder_pkt;
    vpx_codec_iter_t iter = nullptr;
    unsigned int frames_encoded = 0;
    size_t frame_size = 0;

    while ((encoder_pkt = vpx_codec_get_cx_data(&impl_->ctx, &iter))) {
        if (encoder_pkt->kind != VPX_CODEC_CX_FRAME_PKT) {
            continue;
        }

        frames_encoded++;
        if (frames_encoded > 1) {
            throw std::runtime_error("Multiple frames were encoded at once");
        }

        frame_size = encoder_pkt->data.frame.sz;
        if (frame_size == 0) {
            throw std::runtime_error("Encoded frame size is zero");
        }

        const uint8_t* buf_ptr = reinterpret_cast<const uint8_t*>(encoder_pkt->data.frame.buf);
        const uint8_t* buf_end = buf_ptr + frame_size;

        const size_t max_payload = 1200; // choose to fit your RTP payload design
        const uint16_t frag_cnt = static_cast<uint16_t>((frame_size + max_payload - 1) / max_payload);

        const bool is_key = (encoder_pkt->data.frame.flags & VPX_FRAME_IS_KEY) != 0;
        if (is_key) {
            std::cerr << "Encoded key frame, frame_id=" << (impl_->frame_id - 1) << std::endl;
        }

        uint32_t frame_id = impl_->frame_id - 1;
        uint32_t rtp_timestamp = static_cast<uint32_t>(
            (frame_id * 90000) / (impl_->framerate > 0 ? impl_->framerate : 25));

        // Notify SCReAM once per frame
        if (screamTx && *screamTx) {
            (*screamTx)->newMediaFrame(frame_generation_ts / 1000.0,
                                       impl_->ssrc,
                                       static_cast<int>(frame_size),
                                       false);
        }

        for (uint16_t frag_id = 0; frag_id < frag_cnt; ++frag_id) {
            size_t payload_size = std::min(max_payload, static_cast<size_t>(buf_end - buf_ptr));
            bool is_mark = (frag_id == frag_cnt - 1);
            size_t packet_size = kRtpHeaderSize + payload_size;

            uint8_t* pkt_mem = static_cast<uint8_t*>(malloc(packet_size));
            if (!pkt_mem) {
                throw std::runtime_error("malloc failed for RTP packet");
            }

            unsigned short seq = next_seq_++;
            writeRtpHeader(pkt_mem, seq, rtp_timestamp, impl_->ssrc,
                           static_cast<uint8_t>(98 | (is_mark ? 0x80 : 0)));
            memcpy(pkt_mem + kRtpHeaderSize, buf_ptr, payload_size);

            uint64_t send_ts_us = get_timestamp_us();

            bool ok = rtp_queue_.push(pkt_mem,
                                      static_cast<int>(packet_size),
                                      impl_->ssrc,
                                      seq,
                                      is_mark,
                                      send_ts_us / 1e6f,
                                      rtp_timestamp);

            if (!ok) {
                std::cerr << "RtpQueue full, dropping packet frame="
                          << frame_id
                          << " frag=" << frag_id << std::endl;
                free(pkt_mem);
            } else {
                addUnacked(pkt_mem,
                           static_cast<int>(packet_size),
                           frame_id,
                           frag_id,
                           seq,
                           is_mark,
                           rtp_timestamp,
                           send_ts_us);

                std::cout << "Packetized frame=" << frame_id
                          << " frag=" << frag_id
                          << "/" << frag_cnt
                          << " size=" << packet_size
                          << " queue=" << rtp_queue_.sizeOfQueue()
                          << " bytes=" << rtp_queue_.bytesInQueue()
                          << std::endl;
            }

            buf_ptr += payload_size;
        }
    }

    return frame_size;
}