#include "rtp_video_extension.h"

#include <arpa/inet.h>
#include <cstring>

namespace bwvideo {

namespace {
constexpr uint16_t kRtpExtensionProfile = 0xBEDE;
constexpr uint8_t kVideoExtensionId = 1;
constexpr uint8_t kVideoExtensionDataLen = 7;
constexpr uint16_t kRtpExtensionWords = 2;
} // namespace

bool write_rtp_video_extension(uint8_t* rtp_packet,
                               std::size_t rtp_packet_capacity,
                               const RtpVideoExtension& ext)
{
  if (rtp_packet == nullptr || rtp_packet_capacity < kRtpFixedHeaderSize + kRtpVideoExtensionTotalBytes) {
    return false;
  }
  if (ext.frag_cnt == 0 || ext.frag_id >= ext.frag_cnt) {
    return false;
  }

  rtp_packet[0] |= 0x10; // Set X bit.

  const uint16_t profile_n = htons(kRtpExtensionProfile);
  const uint16_t words_n = htons(kRtpExtensionWords);
  std::memcpy(rtp_packet + kRtpFixedHeaderSize + 0, &profile_n, sizeof(profile_n));
  std::memcpy(rtp_packet + kRtpFixedHeaderSize + 2, &words_n, sizeof(words_n));

  uint8_t* ext_data = rtp_packet + kRtpFixedHeaderSize + 4;
  std::memset(ext_data, 0, 8);
  ext_data[0] = static_cast<uint8_t>((kVideoExtensionId << 4) | (kVideoExtensionDataLen - 1));
  ext_data[1] = ext.frame_is_keyframe ? 0x80 : 0x00;
  ext_data[2] = static_cast<uint8_t>(ext.frame_id >> 8);
  ext_data[3] = static_cast<uint8_t>(ext.frame_id & 0xFF);
  ext_data[4] = static_cast<uint8_t>(ext.frag_id >> 8);
  ext_data[5] = static_cast<uint8_t>(ext.frag_id & 0xFF);
  ext_data[6] = static_cast<uint8_t>(ext.frag_cnt >> 8);
  ext_data[7] = static_cast<uint8_t>(ext.frag_cnt & 0xFF);
  return true;
}

bool parse_rtp_video_extension(const uint8_t* rtp_packet,
                               std::size_t rtp_packet_size,
                               RtpVideoExtension* ext,
                               std::size_t* payload_offset)
{
  if (rtp_packet == nullptr || payload_offset == nullptr || rtp_packet_size < kRtpFixedHeaderSize) {
    return false;
  }

  const uint8_t cc = rtp_packet[0] & 0x0F;
  const bool has_extension = (rtp_packet[0] & 0x10) != 0;
  std::size_t offset = kRtpFixedHeaderSize + cc * 4;
  if (rtp_packet_size < offset) {
    return false;
  }

  if (!has_extension) {
    *payload_offset = offset;
    return true;
  }
  if (rtp_packet_size < offset + 4) {
    return false;
  }

  uint16_t profile_n = 0;
  uint16_t words_n = 0;
  std::memcpy(&profile_n, rtp_packet + offset + 0, sizeof(profile_n));
  std::memcpy(&words_n, rtp_packet + offset + 2, sizeof(words_n));
  const uint16_t profile = ntohs(profile_n);
  const std::size_t ext_bytes = static_cast<std::size_t>(ntohs(words_n)) * 4;
  const std::size_t ext_start = offset + 4;
  const std::size_t ext_end = ext_start + ext_bytes;
  if (rtp_packet_size < ext_end) {
    return false;
  }
  *payload_offset = ext_end;

  if (ext == nullptr || profile != kRtpExtensionProfile) {
    return true;
  }

  std::size_t pos = ext_start;
  while (pos < ext_end) {
    const uint8_t hdr = rtp_packet[pos++];
    if (hdr == 0) {
      continue; // padding
    }
    const uint8_t id = hdr >> 4;
    if (id == 15) {
      break;
    }
    const std::size_t len = static_cast<std::size_t>(hdr & 0x0F) + 1;
    if (pos + len > ext_end) {
      return false;
    }
    if (id == kVideoExtensionId && len == kVideoExtensionDataLen) {
      ext->frame_is_keyframe = (rtp_packet[pos + 0] & 0x80) != 0;
      ext->frame_id = static_cast<uint16_t>((rtp_packet[pos + 1] << 8) | rtp_packet[pos + 2]);
      ext->frag_id = static_cast<uint16_t>((rtp_packet[pos + 3] << 8) | rtp_packet[pos + 4]);
      ext->frag_cnt = static_cast<uint16_t>((rtp_packet[pos + 5] << 8) | rtp_packet[pos + 6]);
      return ext->frag_cnt != 0 && ext->frag_id < ext->frag_cnt;
    }
    pos += len;
  }
  return true;
}

} // namespace bwvideo
