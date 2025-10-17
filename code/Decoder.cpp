#include "Decoder.h"
#include <vpx/vp8dx.h>
#include <vpx/vpx_decoder.h>
#include <stdexcept>
#include <vector>
#include <cstring>

struct Decoder::Impl {
    vpx_codec_ctx_t ctx{};
    vpx_codec_dec_cfg_t cfg{};
    int max_threads = 4;
};

Decoder::Decoder(int max_threads) : impl_(new Impl()) {
    impl_->max_threads = max_threads;
    impl_->cfg.threads = max_threads;
    impl_->cfg.w = 0;
    impl_->cfg.h = 0;
    if (vpx_codec_dec_init(&impl_->ctx, &vpx_codec_vp9_dx_algo, &impl_->cfg, 0) != VPX_CODEC_OK) {
        throw std::runtime_error("vpx_codec_dec_init failed");
    }
}

Decoder::~Decoder() {
    vpx_codec_destroy(&impl_->ctx);
    delete impl_;
}

bool Decoder::decodeFrame(const std::vector<uint8_t> &vp9_frame, std::vector<uint8_t> &out_frame, int &out_w, int &out_h) {
    if (vpx_codec_decode(&impl_->ctx, vp9_frame.data(), (unsigned int)vp9_frame.size(), NULL, 0) != VPX_CODEC_OK) {
        return false;
    }

    vpx_image_t *img = NULL;
    vpx_codec_iter_t iter = NULL;
    if ((img = vpx_codec_get_frame(&impl_->ctx, &iter)) != NULL) {
        int w = img->d_w;
        int h = img->d_h;
        out_w = w;
        out_h = h;
        size_t y_size = (size_t)w * h;
        size_t uv_size = y_size / 4;
        out_frame.resize(y_size + 2 * uv_size);
        // Copy Y plane
        for (int r = 0; r < h; ++r) {
            memcpy(out_frame.data() + r * w, img->planes[VPX_PLANE_Y] + r * img->stride[VPX_PLANE_Y], w);
        }
        // U plane
        int half_h = h / 2;
        int half_w = w / 2;
        uint8_t *u_dst = out_frame.data() + y_size;
        for (int r = 0; r < half_h; ++r) {
            memcpy(u_dst + r * half_w, img->planes[VPX_PLANE_U] + r * img->stride[VPX_PLANE_U], half_w);
        }
        // V plane
        uint8_t *v_dst = out_frame.data() + y_size + uv_size;
        for (int r = 0; r < half_h; ++r) {
            memcpy(v_dst + r * half_w, img->planes[VPX_PLANE_V] + r * img->stride[VPX_PLANE_V], half_w);
        }
        return true;
    }
    return false;
}
