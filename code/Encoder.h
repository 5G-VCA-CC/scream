#ifndef BW_VIDEO_ENCODER_H
#define BW_VIDEO_ENCODER_H

#include <cstdio>
#include <cstdint>
#include <pthread.h>
#include <string>
#include <vector>

class RtpQueue;

extern "C" {
#include <vpx/vpx_encoder.h>
#include <vpx/vp8cx.h>
}

class ScreamV2Tx;
namespace bwvideo {

class Encoder
{
public:
  Encoder(const std::string& y4m_path,
          uint16_t fps,
          ScreamV2Tx* screamTx = nullptr,
          pthread_mutex_t* lock_scream = nullptr,
          RtpQueue* rtp_queue = nullptr,
          pthread_mutex_t* lock_rtp_queue = nullptr,
          uint32_t ssrc = 0,
          bool keyframe_unacked = false);
  struct EnqueuedPacketInfo {
    int size_bytes {0};
    bool is_mark {false};
  };

  struct EnqueueResult {
    std::vector<EnqueuedPacketInfo> enqueued_packets;
    bool is_key_frame {false};
    uint32_t dropped_packets {0};
  };

  ~Encoder();

  bool encode_next_frame(uint32_t target_bitrate_bps,
                         int mtu,
                         uint32_t time_ntp,
                         std::vector<std::vector<uint8_t>>& payloads,
                         bool* is_key_frame = nullptr,
                         bool force_key_frame = false);
  bool encode_next_frame_and_enqueue(uint32_t target_bitrate_bps,
                                     int mtu,
                                     uint32_t ssrc,
                                     uint16_t& seq_nr,
                                     uint32_t rtp_timestamp,
                                     float enqueue_ts_s,
                                     EnqueueResult& result,
                                     bool force_key_frame = false,
                                     bool include_video_extension = false);
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
  RtpQueue* rtp_queue_ {nullptr};
  pthread_mutex_t* lock_rtp_queue_ {nullptr};

  vpx_codec_ctx_t ctx_ {};
  vpx_codec_enc_cfg_t cfg_ {};

  ScreamV2Tx* screamTx_ {nullptr};
  pthread_mutex_t* lock_scream_ {nullptr};
  uint32_t ssrc_ {0};
  bool keyframe_unacked_ {false};
  uint16_t last_triggered_seq_ {0};
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
