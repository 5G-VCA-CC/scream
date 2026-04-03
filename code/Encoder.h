#ifndef BW_VIDEO_ENCODER_H
#define BW_VIDEO_ENCODER_H

#include <cstdio>
#include <cstdint>
#include <string>
#include <vector>

extern "C" {
#include <vpx/vpx_encoder.h>
#include <vpx/vp8cx.h>
}

namespace bwvideo {

class Encoder
{
public:
  Encoder(const std::string& y4m_path, uint16_t fps);
  ~Encoder();

  bool encode_next_frame(uint32_t target_bitrate_bps,
                         int mtu,
                         std::vector<std::vector<uint8_t>>& payloads,
                         bool* is_key_frame = nullptr,
                         bool force_key_frame = false);
  void set_periodic_keyframe_interval(float interval_s);
  void disable_periodic_keyframes();

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
  bool periodic_keyframes_enabled_ {false};
  uint16_t keyframe_interval_frames_ {0};

  vpx_codec_ctx_t ctx_ {};
  vpx_codec_enc_cfg_t cfg_ {};

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
