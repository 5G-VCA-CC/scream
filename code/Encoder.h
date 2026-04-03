#ifndef BW_VIDEO_ENCODER_H
#define BW_VIDEO_ENCODER_H

#include <cstdio>
#include <cstdint>
#include <string>
#include <vector>
#include <pthread.h>

extern "C" {
#include <vpx/vpx_encoder.h>
#include <vpx/vp8cx.h>
}

class ScreamV2Tx;

namespace bwvideo {

class Encoder
{
public:
  Encoder(const std::string& y4m_path, uint16_t fps, ScreamV2Tx* screamTx, pthread_mutex_t* lock_scream, uint32_t ssrc, bool keyframe_unacked);
  ~Encoder();

  bool encode_next_frame(uint32_t target_bitrate_bps,
                         int mtu,
                         std::vector<std::vector<uint8_t>>& payloads,
                         bool* is_key_frame = nullptr,
                         bool force_key_frame = false);

  uint16_t width() const { return width_; }
  uint16_t height() const { return height_; }

  Encoder(const Encoder&) = delete;
  Encoder& operator=(const Encoder&) = delete;
  Encoder(Encoder&&) = delete;
  Encoder& operator=(Encoder&&) = delete;

private:
  FILE* fp_ {nullptr};
  long first_frame_offset_ {0};
  uint16_t width_ {0};
  uint16_t height_ {0};
  uint16_t fps_ {0};
  uint32_t frame_id_ {0};
  uint32_t target_bitrate_kbps_ {0};
  uint16_t keyframe_interval_frames_ {30};

  vpx_codec_ctx_t ctx_ {};
  vpx_codec_enc_cfg_t cfg_ {};

  ScreamV2Tx* screamTx_;
  pthread_mutex_t* lock_scream_;
  uint32_t ssrc_;
  bool keyframe_unacked_;
  uint16_t last_triggered_seq_;
  uint32_t last_keyframe_ts_;

  size_t frame_size_bytes() const;
  void parse_y4m_header();
  bool rewind_to_first_frame();
  bool read_y4m_frame(std::vector<uint8_t>& frame);
  bool init_codec();
  void destroy_codec();
  void set_target_bitrate_kbps(uint32_t bitrate_kbps);
};

} // namespace bwvideo

#endif // BW_VIDEO_ENCODER_H
