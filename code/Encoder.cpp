#include "Encoder.h"
#include <vpx/vpx_encoder.h>
#include <vpx/vp8cx.h>
#include <arpa/inet.h>
#include <memory>
#include <cstring>
#include <stdexcept>

#include "RtpQueue.h"
#include "ScreamV2Tx.h"

struct Encoder::Impl
{
    vpx_codec_ctx_t ctx{};
    vpx_codec_enc_cfg_t cfg{};
    int width;
    int height;
    int framerate;
    unsigned int bitrate_kbps;
    uint64_t frame_id = 0;
};

extern void writeRtp(unsigned char *buf, uint16_t seqNr, uint32_t timeStamp, unsigned char pt);

Encoder::Encoder(int width, int height, int framerate, unsigned int bitrate_kbps)
    : impl_(new Impl())
{
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
    impl_->cfg.rc_end_usage = VPX_VBR;
    impl_->cfg.rc_buf_initial_sz = 500;
    impl_->cfg.rc_buf_optimal_sz = 600;
    impl_->cfg.rc_buf_sz = 1000;
    impl_->cfg.rc_min_quantizer = 2;
    impl_->cfg.rc_max_quantizer = 52;
    impl_->cfg.rc_undershoot_pct = 50;
    impl_->cfg.rc_overshoot_pct = 50;
    impl_->cfg.rc_target_bitrate = bitrate_kbps;

    if (vpx_codec_enc_init(&impl_->ctx, &vpx_codec_vp9_cx_algo, &impl_->cfg, 0) != VPX_CODEC_OK)
        throw std::runtime_error("vpx_codec_enc_init failed");

    // reasonable defaults for realtime
    vpx_codec_control(&impl_->ctx, VP8E_SET_CPUUSED, 4);
    vpx_codec_control(&impl_->ctx, VP9E_SET_TILE_COLUMNS, 2);
    vpx_codec_control(&impl_->ctx, VP9E_SET_ROW_MT, 1);
}

Encoder::~Encoder()
{
    vpx_codec_destroy(&impl_->ctx);
    delete impl_;
}

void Encoder::set_target_bitrate(unsigned int bitrate_kbps)
{
    if (!impl_)
        return;
    if (bitrate_kbps == impl_->bitrate_kbps)
        return;
    impl_->bitrate_kbps = bitrate_kbps;
    impl_->cfg.rc_target_bitrate = bitrate_kbps;
    vpx_codec_enc_config_set(&impl_->ctx, &impl_->cfg);
}

std::vector<uint8_t> Encoder::compress_frame(const std::vector<uint8_t> &yuv_frame,
                             uint32_t ts,
                             uint32_t time_ntp,
                             uint32_t ssrc,
                             int mtu,
                             uint16_t &seq_nr,
                             RtpQueue *rtp_queue,
                             ScreamV2Tx *screamTx)
{
    const auto frame_generation_ts = ts;

    std::vector<uint8_t> encoded_frame = encode_frame(yuv_frame);
    packetize_encoded_frame(
        encoded_frame,
        ts,
        time_ntp,
        ssrc,
        mtu,
        seq_nr,
        rtp_queue,
        screamTx);
    return encoded_frame;
}

std::vector<uint8_t> Encoder::encode_frame(const std::vector<uint8_t> &yuv_frame)
{
    if (!impl_)
        return {};
    const int w = impl_->width;
    const int h = impl_->height;
    const size_t y_size = (size_t)w * h;
    const size_t uv_size = y_size / 4;
    if (yuv_frame.size() < y_size + 2 * uv_size)
        throw std::runtime_error("yuv frame too small");

    vpx_image_t *img = vpx_img_alloc(NULL, VPX_IMG_FMT_I420, w, h, 1);
    memcpy(img->planes[VPX_PLANE_Y], yuv_frame.data(), y_size);
    memcpy(img->planes[VPX_PLANE_U], yuv_frame.data() + y_size, uv_size);
    memcpy(img->planes[VPX_PLANE_V], yuv_frame.data() + y_size + uv_size, uv_size);

    if (vpx_codec_encode(&impl_->ctx, img, impl_->frame_id++, 1, 0, VPX_DL_REALTIME) != VPX_CODEC_OK)
    {
        vpx_img_free(img);
        throw std::runtime_error("vpx_codec_encode failed");
    }

    std::vector<uint8_t> out;
    vpx_codec_iter_t iter = NULL;
    const vpx_codec_cx_pkt_t *pkt;
    while ((pkt = vpx_codec_get_cx_data(&impl_->ctx, &iter)))
    {
        if (pkt->kind == VPX_CODEC_CX_FRAME_PKT)
        {
            const uint8_t *b = (const uint8_t *)pkt->data.frame.buf;
            out.insert(out.end(), b, b + pkt->data.frame.sz);
        }
    }

    vpx_img_free(img);
    return out;
}

size_t Encoder::packetize_encoded_frame(const std::vector<uint8_t> &encoded_frame,
                                        uint32_t ts,
                                        uint32_t time_ntp,
                                        uint32_t ssrc,
                                        int mtu,
                                        uint16_t &seq_nr,
                                        RtpQueue *rtp_queue,
                                        ScreamV2Tx *screamTx)
{
    if (!rtp_queue || encoded_frame.empty() || mtu <= 0)
    {
        return 0;
    }

    const size_t frame_size = encoded_frame.size();
    const size_t rtp_header_size = 12;
    const size_t max_payload_size = static_cast<size_t>(mtu);
    size_t offset = 0;

    while (offset < frame_size)
    {
        size_t payload_size = std::min(max_payload_size, frame_size - offset);
        bool isMark = (offset + payload_size == frame_size);

        int recvlen = static_cast<int>(rtp_header_size + payload_size);
        unsigned char *buf_rtp = (unsigned char *)malloc(recvlen);
        if (!buf_rtp)
        {
            throw std::runtime_error("malloc failed in packetize_encoded_frame");
        }

        unsigned char pt = 98;
        if (isMark)
            pt |= 0x80;

        writeRtp(buf_rtp, seq_nr, ts, pt);
        memcpy(buf_rtp + rtp_header_size, encoded_frame.data() + offset, payload_size);

        rtp_queue->push(buf_rtp,
                        recvlen,
                        ssrc,
                        seq_nr,
                        isMark,
                        (time_ntp) / 65536.0f,
                        ts);

        if (screamTx)
        {
            screamTx->newMediaFrame(time_ntp, ssrc, recvlen, isMark);
        }
        float rateTx = screamTx->getTargetBitrate(time_ntp, ssrc);
        std::cout << "SCReAM target bitrate: " << rateTx / 1000 << " kbps" << std::endl;
        set_target_bitrate(rateTx / 1000);
        seq_nr++;
        offset += payload_size;
    }

    return frame_size;
}
