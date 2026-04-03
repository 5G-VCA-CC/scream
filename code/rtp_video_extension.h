#ifndef BW_VIDEO_RTP_VIDEO_EXTENSION_H
#define BW_VIDEO_RTP_VIDEO_EXTENSION_H

#include <cstddef>
#include <cstdint>

namespace bwvideo {

struct RtpVideoExtension {
  bool frame_is_keyframe {false};
  uint16_t frame_id {0};
  uint16_t frag_id {0};
  uint16_t frag_cnt {0};
};

constexpr std::size_t kRtpFixedHeaderSize = 12;
constexpr std::size_t kRtpVideoExtensionTotalBytes = 12;

bool write_rtp_video_extension(uint8_t* rtp_packet,
                               std::size_t rtp_packet_capacity,
                               const RtpVideoExtension& ext);

bool parse_rtp_video_extension(const uint8_t* rtp_packet,
                               std::size_t rtp_packet_size,
                               RtpVideoExtension* ext,
                               std::size_t* payload_offset);

} // namespace bwvideo

#endif // BW_VIDEO_RTP_VIDEO_EXTENSION_H
