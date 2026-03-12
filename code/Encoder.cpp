#include "Encoder.h"
#include <vpx/vpx_encoder.h>
#include <vpx/vp8cx.h>
#include <memory>
#include <cstring>
#include <stdexcept>
#include <limits>
#include <sys/time.h>
#include <iostream>
#include <pthread.h>

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

    // Feedback-timeout key frame control (emulates ringmaster's MAX_UNACKED_US)
    bool use_feedback_timeout_keyframes = false;
    uint64_t max_unacked_us = 1000000; // default 1s (matches ringmaster)
    bool has_triggered = false;
    uint16_t last_triggered_seq = 0;

    // One-shot forced key frame (set by forceNextKeyframe(), cleared after use)
    bool force_keyframe = false;

    // ScreamV2Tx object to access txPackets data
    ScreamV2Tx* screamTx;
    uint32_t ssrc;
};

// Helper to get current timestamp in microseconds
static uint64_t get_timestamp_us() {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (uint64_t)tv.tv_sec * 1000000 + tv.tv_usec;
}

Encoder::Encoder(int width, int height, int framerate, unsigned int bitrate_kbps, ScreamV2Tx* screamTx, uint32_t ssrc)
    : impl_(new Impl()) {
    impl_->width = width;
    impl_->height = height;
    impl_->framerate = framerate;
    impl_->bitrate_kbps = bitrate_kbps;
    impl_->screamTx = screamTx;
    impl_->ssrc = ssrc;

    if (vpx_codec_enc_config_default(&vpx_codec_vp9_cx_algo, &impl_->cfg, 0) != VPX_CODEC_OK)
        throw std::runtime_error("vpx_codec_enc_config_default failed");

    impl_->cfg.g_w = width;
    impl_->cfg.g_h = height;
    impl_->cfg.g_timebase.num = 1;
    impl_->cfg.g_timebase.den = framerate > 0 ? framerate : 25;
    impl_->cfg.g_pass = VPX_RC_ONE_PASS;
    impl_->cfg.g_lag_in_frames = 0;
    impl_->cfg.g_error_resilient = VPX_ERROR_RESILIENT_DEFAULT;
    impl_->cfg.g_threads = 4; // Match ringmaster: encoder threads equal to column tiles
    impl_->cfg.rc_resize_allowed = 0; // Match ringmaster: disable spatial sampling
    impl_->cfg.rc_dropframe_thresh = 0; // Match ringmaster: disable frame dropping

    // Tighten rate-control buffers so we react quickly to bandwidth drops
    impl_->cfg.rc_buf_initial_sz = 500;
    impl_->cfg.rc_buf_optimal_sz = 600;
    impl_->cfg.rc_buf_sz = 1000;

    // Allow the encoder to raise QP aggressively while staying within CBR
    impl_->cfg.rc_min_quantizer = 2; // Match ringmaster: QP range 2-52
    impl_->cfg.rc_max_quantizer = 52;
    impl_->cfg.rc_undershoot_pct = 50;
    impl_->cfg.rc_overshoot_pct = 50;

    // Prevent libvpx encoder from automatically placing key frames (match ringmaster)
    impl_->cfg.kf_mode = VPX_KF_DISABLED;
    impl_->cfg.kf_max_dist = std::numeric_limits<unsigned int>::max();
    impl_->cfg.kf_min_dist = 0;

    impl_->cfg.rc_end_usage = VPX_CBR;
    impl_->cfg.rc_target_bitrate = bitrate_kbps;

    if (vpx_codec_enc_init(&impl_->ctx, &vpx_codec_vp9_cx_algo, &impl_->cfg, 0) != VPX_CODEC_OK)
        throw std::runtime_error("vpx_codec_enc_init failed");

    // reasonable defaults for realtime
    vpx_codec_control(&impl_->ctx, VP8E_SET_CPUUSED, 12);
    vpx_codec_control(&impl_->ctx, VP9E_SET_TILE_COLUMNS, 2);
    vpx_codec_control(&impl_->ctx, VP9E_SET_ROW_MT, 1);

    // Clamp keyframe bitrate spikes so sudden I-frames stay within budget
    vpx_codec_control(&impl_->ctx, VP8E_SET_MAX_INTRA_BITRATE_PCT, 900);

    // OPTIONAL: latency-friendly quality tuning (disable to revert to baseline behaviour)
    vpx_codec_control(&impl_->ctx, VP8E_SET_STATIC_THRESHOLD, 1);
    vpx_codec_control(&impl_->ctx, VP9E_SET_AQ_MODE, 3);
    vpx_codec_control(&impl_->ctx, VP9E_SET_NOISE_SENSITIVITY, 1);
    vpx_codec_control(&impl_->ctx, VP9E_SET_FRAME_PARALLEL_DECODING, 0);
}

Encoder::~Encoder() {
    vpx_codec_destroy(&impl_->ctx);
    delete impl_;
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

// Configure the encoder to use feedback timeouts to force keyframes
void Encoder::setFeedbackTimeoutKeyframes(bool enable, uint64_t timeout_us) {
    if (!impl_) return;
    impl_->use_feedback_timeout_keyframes = enable;
}

// Called by scream_sender to notify the encoder when RTCP feedback is received
// void Encoder::notifyFeedbackReceived() {
//     if (!impl_) return;
//     impl_->last_feedback_ts_us = get_timestamp_us();
//     impl_->feedback_ever_received = true;
// }

void Encoder::forceNextKeyframe() {
    if (!impl_) return;
    impl_->force_keyframe = true;
}

std::vector<uint8_t> Encoder::encodeFrame(const std::vector<uint8_t> &yuv_frame) {
    if (!impl_) return {};
    const int w = impl_->width;
    const int h = impl_->height;
    const size_t y_size = (size_t)w * h;
    const size_t uv_size = y_size / 4;
    if (yuv_frame.size() < y_size + 2 * uv_size) throw std::runtime_error("yuv frame too small");

    vpx_image_t *img = vpx_img_alloc(NULL, VPX_IMG_FMT_I420, w, h, 1);
    memcpy(img->planes[VPX_PLANE_Y], yuv_frame.data(), y_size);
    memcpy(img->planes[VPX_PLANE_U], yuv_frame.data() + y_size, uv_size);
    memcpy(img->planes[VPX_PLANE_V], yuv_frame.data() + y_size + uv_size, uv_size);

    // Check if we need to force a key frame
    vpx_enc_frame_flags_t flags = 0;

    // One-shot forced key frame (e.g. loss-triggered)
    if (impl_->force_keyframe) {
        flags = VPX_EFLAG_FORCE_KF;
        impl_->force_keyframe = false;
        impl_->last_keyframe_ts_us = get_timestamp_us();
        std::cerr << "* Loss-triggered key frame forced at frame " << impl_->frame_id << std::endl;
    }
    // Periodic key frame timer
    else if (impl_->use_periodic_keyframes) {

    // One-shot forced key frame (e.g. loss-triggered)
    if (impl_->force_keyframe) {
        flags = VPX_EFLAG_FORCE_KF;
        impl_->force_keyframe = false;
        impl_->last_keyframe_ts_us = get_timestamp_us();
        std::cerr << "* Loss-triggered key frame forced at frame " << impl_->frame_id << std::endl;
    }
    // Periodic key frame timer
    else if (impl_->use_periodic_keyframes) {
        uint64_t curr_ts = get_timestamp_us();
        if (impl_->last_keyframe_ts_us == 0 || 
            curr_ts - impl_->last_keyframe_ts_us >= impl_->keyframe_interval_us) {
            flags = VPX_EFLAG_FORCE_KF;
            impl_->last_keyframe_ts_us = curr_ts;
            std::cerr << "* Periodic key frame forced at frame " << impl_->frame_id 
                     << " (interval: " << impl_->keyframe_interval_us / 1000 << " ms)" << std::endl;
        }
    }
    // Force a keyframe if the last transmitted packet has been unacked for longer than 1s (max_unacked_us)
    else if (impl_->use_feedback_timeout_keyframes && impl_->screamTx) {
        uint16_t oldest_unacked_seq = 0;
        uint32_t oldest_unacked_ts = 0;
        if (impl_->screamTx->getOldestUnacked(impl_->ssrc, oldest_unacked_seq, oldest_unacked_ts)) {
            uint32_t us_since_first_send = get_timestamp_us() - oldest_unacked_ts;
            if (us_since_first_send > impl_->max_unacked_us) {
                if (impl_->last_triggered_seq != oldest_unacked_seq) {
                    flags = VPX_EFLAG_FORCE_KF;
                    impl_->last_triggered_seq = oldest_unacked_seq;
                }
            }
        }
    }

    if (vpx_codec_encode(&impl_->ctx, img, impl_->frame_id++, 1, flags, VPX_DL_REALTIME) != VPX_CODEC_OK) {
        vpx_img_free(img);
        throw std::runtime_error("vpx_codec_encode failed");
    }

    std::vector<uint8_t> out;
    vpx_codec_iter_t iter = NULL;
    const vpx_codec_cx_pkt_t *pkt;
    while ((pkt = vpx_codec_get_cx_data(&impl_->ctx, &iter))) {
        if (pkt->kind == VPX_CODEC_CX_FRAME_PKT) {
            const uint8_t* b = (const uint8_t*)pkt->data.frame.buf;
            out.insert(out.end(), b, b + pkt->data.frame.sz);
        }
    }

    vpx_img_free(img);
    return out;
}
