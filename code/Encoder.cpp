#include "Encoder.h"
#include "ScreamTx.h"
#include "RtpQueue.h"
#include "rtp_video_extension.h"

#include <algorithm>
#include <arpa/inet.h>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <stdexcept>

using namespace std;

namespace bwvideo {
namespace {
void write_rtp_header(uint8_t* buf,
                      uint16_t seq_nr,
                      uint32_t time_stamp,
                      unsigned char pt,
                      uint32_t ssrc)
{
  const uint16_t seq_nr_network = htons(seq_nr);
  const uint32_t ts_network = htonl(time_stamp);
  const uint32_t ssrc_network = htonl(ssrc);
  memcpy(buf, "\x80\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00", 12);
  memcpy(buf + 1, &pt, 1);
  memcpy(buf + 2, &seq_nr_network, 2);
  memcpy(buf + 4, &ts_network, 4);
  memcpy(buf + 8, &ssrc_network, 4);
}
} // namespace

Encoder::Encoder(const std::string& y4m_path,
                 uint16_t fps,
                 ScreamV2Tx* screamTx,
                 pthread_mutex_t* lock_scream,
                 RtpQueue* rtp_queue,
                 pthread_mutex_t* lock_rtp_queue,
                 uint32_t ssrc,
                 bool keyframe_unacked)
  : fps_(fps),
    periodic_keyframes_enabled_(true),
    keyframe_interval_frames_(std::max<uint16_t>(fps_, 30)),
    rtp_queue_(rtp_queue),
    lock_rtp_queue_(lock_rtp_queue),
    screamTx_(screamTx),
    lock_scream_(lock_scream),
    ssrc_(ssrc),
    keyframe_unacked_(keyframe_unacked),
    last_triggered_seq_(0)
{
  fp_ = fopen(y4m_path.c_str(), "rb");
  if (!fp_) {
    throw runtime_error("Failed to open Y4M input");
  }
  parse_y4m_header();
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

void Encoder::set_periodic_keyframe_interval(float interval_s)
{
  if (interval_s <= 0.0f) {
    disable_periodic_keyframes();
    return;
  }
  periodic_keyframes_enabled_ = true;
  keyframe_interval_frames_ = static_cast<uint16_t>(
    std::max(1.0f, std::round(interval_s * std::max<uint16_t>(1, fps_))));
}

void Encoder::disable_periodic_keyframes()
{
  periodic_keyframes_enabled_ = false;
  keyframe_interval_frames_ = 0;
}

bool Encoder::encode_next_frame(uint32_t target_bitrate_bps,
                                int mtu,
                                uint32_t time_ntp,
                                std::vector<std::vector<uint8_t>>& payloads,
                                bool* is_key_frame,
                                bool force_key_frame,
                                bool allow_keyframe_force)
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
  if (frame_id_ == 0 ||
      (allow_keyframe_force &&
       periodic_keyframes_enabled_ &&
       keyframe_interval_frames_ > 0 &&
       (frame_id_ % keyframe_interval_frames_ == 0))) {
    encode_flags |= VPX_EFLAG_FORCE_KF;
  }
  if (force_key_frame && allow_keyframe_force) {
    encode_flags |= VPX_EFLAG_FORCE_KF;
  }
  else if (keyframe_unacked_ && screamTx_ && lock_scream_ && lock_rtp_queue_) {
    const uint32_t kOneSecondQ16 = 65536u;
    uint16_t oldest_unacked_seq = 0;
    uint32_t oldest_unacked_tx_ntp = 0;
    pthread_mutex_lock(lock_scream_);
    const bool has_oldest_unacked = screamTx_->getOldestUnacked(ssrc_, oldest_unacked_seq, oldest_unacked_tx_ntp);
    bool should_force_recovery_keyframe = false;
    if (has_oldest_unacked) {
      uint32_t age_ntp = time_ntp - oldest_unacked_tx_ntp;
      if (age_ntp > kOneSecondQ16 && allow_keyframe_force) {
        if (last_triggered_seq_ != oldest_unacked_seq) {
          should_force_recovery_keyframe = true;
          encode_flags |= VPX_EFLAG_FORCE_KF;
          last_triggered_seq_ = oldest_unacked_seq;
        }
      }
    }
    if (should_force_recovery_keyframe) {
      /*
       * Keep SCReAM state reset atomic vs TX/RTP queue threads.
       */
      pthread_mutex_lock(lock_rtp_queue_);
      uint32_t rtp_queue_cleared = 0;
      uint32_t tx_packets_cleared = 0;
      uint32_t bytes_in_flight_cleared = 0;
      screamTx_->resetStreamForRecoveryKeyframe(ssrc_,
                                                rtp_queue_cleared,
                                                tx_packets_cleared,
                                                bytes_in_flight_cleared);
      pthread_mutex_unlock(lock_rtp_queue_);
    }
    pthread_mutex_unlock(lock_scream_);
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

bool Encoder::encode_next_frame_and_enqueue(uint32_t target_bitrate_bps,
                                            int mtu,
                                            uint32_t ssrc,
                                            uint16_t& seq_nr,
                                            uint32_t rtp_timestamp,
                                            float enqueue_ts_s,
                                            EnqueueResult& result,
                                            bool force_key_frame,
                                            bool include_video_extension,
                                            bool allow_keyframe_force)
{
  result.enqueued_packets.clear();
  result.is_key_frame = false;
  result.dropped_packets = 0;
  if (mtu <= 0 || !rtp_queue_ || !lock_rtp_queue_) {
    return false;
  }

  std::vector<std::vector<uint8_t>> payloads;
  bool is_key_frame = false;
  const uint32_t time_ntp = static_cast<uint32_t>(enqueue_ts_s * 65536.0f);
  if (!encode_next_frame(target_bitrate_bps,
                         mtu,
                         time_ntp,
                         payloads,
                         &is_key_frame,
                         force_key_frame,
                         allow_keyframe_force)) {
    return false;
  }
  if (payloads.size() > 0xFFFFu) {
    return false;
  }

  result.is_key_frame = is_key_frame;
  const uint16_t frame_id = static_cast<uint16_t>(frame_id_ - 1);
  const uint16_t frag_cnt = static_cast<uint16_t>(payloads.size());

  for (size_t i = 0; i < payloads.size(); i++) {
    const bool is_mark = (i + 1 == payloads.size());
    const int packet_size = static_cast<int>(payloads[i].size()) + 12 +
                            (include_video_extension ? static_cast<int>(kRtpVideoExtensionTotalBytes) : 0);
    unsigned char pt = 98;
    if (is_mark) {
      pt |= 0x80;
    }

    uint8_t* buf_rtp = static_cast<uint8_t*>(malloc(packet_size));
    if (!buf_rtp) {
      return false;
    }
    write_rtp_header(buf_rtp, seq_nr, rtp_timestamp, pt, ssrc);

    size_t payload_offset = 12;
    if (include_video_extension) {
      RtpVideoExtension ext;
      ext.frame_is_keyframe = is_key_frame;
      ext.frame_id = frame_id;
      ext.frag_id = static_cast<uint16_t>(i);
      ext.frag_cnt = frag_cnt;
      if (!write_rtp_video_extension(buf_rtp, static_cast<std::size_t>(packet_size), ext)) {
        free(buf_rtp);
        result.dropped_packets++;
        seq_nr++;
        continue;
      }
      payload_offset += kRtpVideoExtensionTotalBytes;
    }

    memcpy(buf_rtp + payload_offset, payloads[i].data(), payloads[i].size());

    pthread_mutex_lock(lock_rtp_queue_);
    const bool pushed = rtp_queue_->push(buf_rtp, packet_size, ssrc, seq_nr, is_mark, enqueue_ts_s, rtp_timestamp);
    pthread_mutex_unlock(lock_rtp_queue_);

    if (pushed) {
      EnqueuedPacketInfo packet_info;
      packet_info.size_bytes = packet_size;
      packet_info.is_mark = is_mark;
      result.enqueued_packets.push_back(packet_info);
    } else {
      free(buf_rtp);
      result.dropped_packets++;
    }

    seq_nr++;
  }

  return true;
}

} // namespace bwvideo
