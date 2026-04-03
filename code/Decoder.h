#ifndef BW_VIDEO_DECODER_H
#define BW_VIDEO_DECODER_H

#include <cstdint>
#include <cstdio>
#include <map>
#include <string>
#include <vector>
#include "rtp_video_extension.h"

extern "C" {
#include <vpx/vpx_decoder.h>
#include <vpx/vp8dx.h>
}

class VideoDisplay;

namespace bwvideo {

class Decoder
{
public:
  Decoder(uint16_t width,
          uint16_t height,
          bool render_video,
          const std::string& output_path = "received.y4m");
  ~Decoder();

  void add_rtp_payload(uint16_t seq_nr,
                       uint32_t timestamp,
                       const uint8_t* payload,
                       size_t payload_size,
                       bool marker,
                       const RtpVideoExtension* ext = nullptr);

  Decoder(const Decoder&) = delete;
  Decoder& operator=(const Decoder&) = delete;
  Decoder(Decoder&&) = delete;
  Decoder& operator=(Decoder&&) = delete;

private:
  struct LegacyFrameAssembly {
    std::map<uint16_t, std::vector<uint8_t>> payloads {};
    bool marker_seen {false};
    uint16_t marker_seq {0};
  };

  struct FrameAssembly {
    bool is_keyframe {false};
    uint16_t frag_cnt {0};
    std::map<uint16_t, std::vector<uint8_t>> fragments {};
  };

  uint16_t width_ {0};
  uint16_t height_ {0};
  bool render_video_ {false};
  FILE* output_ {nullptr};
  vpx_codec_ctx_t ctx_ {};
  std::map<uint32_t, LegacyFrameAssembly> frame_by_ts_ {};
  std::map<uint16_t, FrameAssembly> frame_by_id_ {};
  bool wait_for_keyframe_ {true};
  bool next_expected_frame_valid_ {false};
  uint16_t next_expected_frame_id_ {0};
  VideoDisplay* display_ {nullptr};

  void try_decode_legacy(uint32_t timestamp);
  void try_decode_with_metadata(uint16_t frame_id);
  void write_decoded_frames();
  void write_plane(uint8_t* plane, int stride, int w, int h);
  void cleanup_old_frames();
};

} // namespace bwvideo

#endif // BW_VIDEO_DECODER_H
