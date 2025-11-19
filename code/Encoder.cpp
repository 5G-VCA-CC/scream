#include "Encoder.h"
#include <vpx/vpx_encoder.h>
#include <vpx/vp8cx.h>
#include <memory>
#include <cstring>
#include <stdexcept>
#include <limits>

struct Encoder::Impl {
    vpx_codec_ctx_t ctx{};
    vpx_codec_enc_cfg_t cfg{};
    int width;
    int height;
    int framerate;
    unsigned int bitrate_kbps;
    uint64_t frame_id = 0;
};

Encoder::Encoder(int width, int height, int framerate, unsigned int bitrate_kbps)
    : impl_(new Impl()) {
    impl_->width = width;
    impl_->height = height;
    impl_->framerate = framerate;
    impl_->bitrate_kbps = bitrate_kbps;

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
    vpx_codec_control(&impl_->ctx, VP8E_SET_CPUUSED, 4);
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

    if (vpx_codec_encode(&impl_->ctx, img, impl_->frame_id++, 1, 0, VPX_DL_REALTIME) != VPX_CODEC_OK) {
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
