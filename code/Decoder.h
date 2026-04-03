#ifndef BW_VIDEO_DECODER_H
#define BW_VIDEO_DECODER_H

#include <cstdint>
#include <condition_variable>
#include <cstdio>
#include <deque>
#include <map>
#include <mutex>
#include <string>
#include <thread>
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
  struct QueuedFrame {
    uint32_t timestamp {0};
    std::vector<uint8_t> bitstream {};
  };

  struct FrameAssembly {
    bool is_keyframe {false};
    uint16_t frag_cnt {0};
    std::map<uint16_t, std::vector<uint8_t>> fragments {};
  };
  enum class RecoveryMode {
    kUnknown,
    kMetadata,
    kLegacy
  };

  uint16_t width_ {0};
  uint16_t height_ {0};
  bool render_video_ {false};
  FILE* output_ {nullptr};
  std::map<uint32_t, LegacyFrameAssembly> frame_by_ts_ {};
  std::map<uint16_t, FrameAssembly> frame_by_id_ {};
  RecoveryMode recovery_mode_ {RecoveryMode::kUnknown};
  bool next_expected_frame_valid_ {false};
  uint16_t next_expected_frame_id_ {0};
  std::mutex queue_mutex_ {};
  std::condition_variable queue_cv_ {};
  std::deque<QueuedFrame> decode_queue_ {};
  std::thread worker_thread_ {};
  bool stop_worker_ {false};

  void try_decode_legacy(uint32_t timestamp);
  void try_decode_with_metadata(uint16_t frame_id);
  void enqueue_frame(uint32_t timestamp, std::vector<uint8_t>&& bitstream);
  void worker_main();
  void write_decoded_frames(vpx_codec_ctx_t& ctx, VideoDisplay* display);
  void write_plane(uint8_t* plane, int stride, int w, int h);
  void cleanup_old_frames();
  bool frame_complete(const FrameAssembly& frame) const;
  bool find_complete_keyframe_ahead(uint16_t* frame_id) const;
  void cleanup_metadata_frames_before(uint16_t frame_id);
};

} // namespace bwvideo

#endif // BW_VIDEO_DECODER_H
