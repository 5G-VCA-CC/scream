#include "Encoder.h"
#include "ScreamTx.h"

#include <algorithm>
#include <cstring>
#include <stdexcept>

using namespace std;

namespace bwvideo {

Encoder::Encoder(const std::string& y4m_path, uint16_t fps, ScreamV2Tx* screamTx, pthread_mutex_t* lock_scream, uint32_t ssrc, bool keyframe_unacked)
  : fps_(fps)
{
  fp_ = fopen(y4m_path.c_str(), "rb");
  screamTx_ = screamTx;
  lock_scream_ = lock_scream;
  ssrc_ = ssrc;
  keyframe_unacked_ = keyframe_unacked;
  last_triggered_seq_ = 0;
  if (!fp_) {
    throw runtime_error("Failed to open Y4M input");
  }
  parse_y4m_header();
  keyframe_interval_frames_ = std::max<uint16_t>(fps_, 30);
  if (!init_codec()) {
    throw runtime_error("Failed to initialize VP9 encoder");
  }
}

Encoder::~Encoder()
{
  destroy_codec();
  if (fp_) {
    fclose(fp_);
    fp_ = nullptr;
  }
}

size_t Encoder::frame_size_bytes() const
{
  return static_cast<size_t>(width_) * static_cast<size_t>(height_) * 3 / 2;
}

void Encoder::parse_y4m_header()
{
  char line[256];
  if (!fgets(line, sizeof(line), fp_)) {
    throw runtime_error("Failed to read Y4M header");
  }
  if (strncmp(line, "YUV4MPEG2", 9) != 0) {
    throw runtime_error("Unsupported input format, expected Y4M");
  }

  char* token = strtok(line, " ");
  while (token) {
    if (token[0] == 'W') {
      width_ = static_cast<uint16_t>(atoi(token + 1));
    } else if (token[0] == 'H') {
      height_ = static_cast<uint16_t>(atoi(token + 1));
    }
    token = strtok(nullptr, " ");
  }
  if (width_ == 0 || height_ == 0) {
    throw runtime_error("Invalid Y4M dimensions");
  }

  first_frame_offset_ = ftell(fp_);
}

bool Encoder::rewind_to_first_frame()
{
  return fp_ && fseek(fp_, first_frame_offset_, SEEK_SET) == 0;
}

bool Encoder::read_y4m_frame(std::vector<uint8_t>& frame)
{
  char line[128];
  while (true) {
    if (!fgets(line, sizeof(line), fp_)) {
      if (!rewind_to_first_frame()) {
        return false;
      }
      continue;
    }
    if (strncmp(line, "FRAME", 5) == 0) {
      break;
    }
  }

  frame.resize(frame_size_bytes());
  if (fread(frame.data(), 1, frame.size(), fp_) != frame.size()) {
    if (!rewind_to_first_frame()) {
      return false;
    }
    return read_y4m_frame(frame);
  }
  return true;
}

bool Encoder::init_codec()
{
  if (vpx_codec_enc_config_default(&vpx_codec_vp9_cx_algo, &cfg_, 0) != VPX_CODEC_OK) {
    return false;
  }

  cfg_.g_w = width_;
  cfg_.g_h = height_;
  cfg_.g_timebase.num = 1;
  cfg_.g_timebase.den = std::max<uint16_t>(1, fps_);
  cfg_.g_threads = 4;
  cfg_.g_error_resilient = VPX_ERROR_RESILIENT_DEFAULT;
  cfg_.g_lag_in_frames = 0;
  cfg_.kf_mode = VPX_KF_DISABLED;
  cfg_.rc_end_usage = VPX_CBR;
  cfg_.rc_target_bitrate = 1000;

  if (vpx_codec_enc_init(&ctx_, &vpx_codec_vp9_cx_algo, &cfg_, 0) != VPX_CODEC_OK) {
    return false;
  }

  vpx_codec_control(&ctx_, VP8E_SET_CPUUSED, 8);
  vpx_codec_control(&ctx_, VP9E_SET_ROW_MT, 1);
  vpx_codec_control(&ctx_, VP9E_SET_TILE_COLUMNS, 2);
  return true;
}

void Encoder::destroy_codec()
{
  vpx_codec_destroy(&ctx_);
}

void Encoder::set_target_bitrate_kbps(uint32_t bitrate_kbps)
{
  bitrate_kbps = std::max(100u, bitrate_kbps);
  if (bitrate_kbps == target_bitrate_kbps_) {
    return;
  }

  target_bitrate_kbps_ = bitrate_kbps;
  cfg_.rc_target_bitrate = target_bitrate_kbps_;
  vpx_codec_enc_config_set(&ctx_, &cfg_);
}

bool Encoder::encode_next_frame(uint32_t target_bitrate_bps,
                                int mtu,
                                uint32_t time_ntp,
                                std::vector<std::vector<uint8_t>>& payloads,
                                bool* is_key_frame,
                                bool force_key_frame)
{
  payloads.clear();
  if (is_key_frame) {
    *is_key_frame = false;
  }
  if (mtu <= 0) {
    return false;
  }

  vector<uint8_t> frame;
  if (!read_y4m_frame(frame)) {
    return false;
  }

  set_target_bitrate_kbps(target_bitrate_bps / 1000);

  vpx_image_t raw;
  vpx_img_wrap(&raw, VPX_IMG_FMT_I420, width_, height_, 1, frame.data());
  const uint8_t* y = frame.data();
  const uint8_t* u = y + width_ * height_;
  const uint8_t* v = u + (width_ * height_) / 4;
  raw.planes[VPX_PLANE_Y] = const_cast<uint8_t*>(y);
  raw.planes[VPX_PLANE_U] = const_cast<uint8_t*>(u);
  raw.planes[VPX_PLANE_V] = const_cast<uint8_t*>(v);
  raw.stride[VPX_PLANE_Y] = width_;
  raw.stride[VPX_PLANE_U] = width_ / 2;
  raw.stride[VPX_PLANE_V] = width_ / 2;

  vpx_enc_frame_flags_t encode_flags = 0;
  if (frame_id_ == 0 || (frame_id_ % keyframe_interval_frames_ == 0)) {
    encode_flags |= VPX_EFLAG_FORCE_KF;
  }
  else if (force_key_frame) {
    encode_flags |= VPX_EFLAG_FORCE_KF;
  }
  else if (keyframe_unacked_) {
    const uint32_t kOneSecondQ16 = 65536u;
    uint16_t oldest_unacked_seq = 0;
    uint32_t oldest_unacked_tx_ntp = 0;
    pthread_mutex_lock(lock_scream_);
    const bool has_oldest_unacked = screamTx_->getOldestUnacked(ssrc_, oldest_unacked_seq, oldest_unacked_tx_ntp);
    pthread_mutex_unlock(lock_scream_);
    if (has_oldest_unacked) {
        uint32_t age_ntp = time_ntp - oldest_unacked_tx_ntp;
        if (age_ntp > kOneSecondQ16) {
            if (last_triggered_seq_ != oldest_unacked_seq) {
                encode_flags |= VPX_EFLAG_FORCE_KF;
                last_triggered_seq_ = oldest_unacked_seq;
            }
        }
    }
  }

  if (vpx_codec_encode(&ctx_, &raw, frame_id_, 1, encode_flags, VPX_DL_REALTIME) != VPX_CODEC_OK) {
    return false;
  }

  vpx_codec_iter_t iter = nullptr;
  const vpx_codec_cx_pkt_t* pkt;
  while ((pkt = vpx_codec_get_cx_data(&ctx_, &iter))) {
    if (pkt->kind != VPX_CODEC_CX_FRAME_PKT) {
      continue;
    }
    if (is_key_frame && (pkt->data.frame.flags & VPX_FRAME_IS_KEY)) {
      *is_key_frame = true;
    }
    const uint8_t* ptr = static_cast<const uint8_t*>(pkt->data.frame.buf);
    size_t left = pkt->data.frame.sz;
    while (left > 0) {
      const size_t sz = std::min(static_cast<size_t>(mtu), left);
      payloads.emplace_back(ptr, ptr + sz);
      ptr += sz;
      left -= sz;
    }
  }

  frame_id_++;
  return !payloads.empty();
}

} // namespace bwvideo
