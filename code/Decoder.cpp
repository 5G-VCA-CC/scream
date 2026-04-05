#include "Decoder.h"

#include <algorithm>
#include <iostream>
#include <memory>
#include <stdexcept>

#include "image.hh"
#include "sdl.hh"

using namespace std;

namespace bwvideo {
namespace {
bool frame_id_ahead(uint16_t frame_id, uint16_t reference)
{
  return static_cast<int16_t>(frame_id - reference) > 0;
}
} // namespace

Decoder::Decoder(uint16_t width,
                 uint16_t height,
                 bool render_video,
                 const std::string& output_path)
  : width_(width), height_(height), render_video_(render_video)
{
  output_ = fopen(output_path.c_str(), "wb");
  if (output_) {
    fprintf(output_, "YUV4MPEG2 W%d H%d F30:1 Ip A0:0 C420\n", width_, height_);
  }

  worker_thread_ = std::thread(&Decoder::worker_main, this);
}

Decoder::~Decoder()
{
  {
    std::lock_guard<std::mutex> lock(queue_mutex_);
    stop_worker_ = true;
  }
  queue_cv_.notify_one();
  if (worker_thread_.joinable()) {
    worker_thread_.join();
  }

  if (output_) {
    fclose(output_);
    output_ = nullptr;
  }
}

void Decoder::add_rtp_payload(uint16_t seq_nr,
                              uint32_t timestamp,
                              const uint8_t* payload,
                              size_t payload_size,
                              bool marker,
                              const RtpVideoExtension* ext)
{
  const bool has_valid_metadata = (ext != nullptr && ext->frag_cnt > 0 && ext->frag_id < ext->frag_cnt);
  if (has_valid_metadata) {
    auto& frame = frame_by_id_[ext->frame_id];
    if (frame.frag_cnt == 0) {
      frame.frag_cnt = ext->frag_cnt;
      frame.is_keyframe = ext->frame_is_keyframe;
    } else if (frame.frag_cnt != ext->frag_cnt) {
      frame_by_id_.erase(ext->frame_id);
      return;
    }
    if (frame.fragments.find(ext->frag_id) == frame.fragments.end()) {
      // Keep first valid fragment payload to avoid duplicate overwrite jitter.
      frame.fragments[ext->frag_id] = vector<uint8_t>(payload, payload + payload_size);
    }
    try_decode_with_metadata(ext->frame_id);
  } else {
    auto& frame = frame_by_ts_[timestamp];
    frame.payloads[seq_nr] = vector<uint8_t>(payload, payload + payload_size);
    if (marker) {
      frame.marker_seen = true;
      frame.marker_seq = seq_nr;
    }
    try_decode_legacy(timestamp);
  }
  cleanup_old_frames();
}

void Decoder::try_decode_legacy(uint32_t timestamp)
{
  auto it = frame_by_ts_.find(timestamp);
  if (it == frame_by_ts_.end()) {
    return;
  }

  LegacyFrameAssembly& frame = it->second;
  if (!frame.marker_seen || frame.payloads.empty()) {
    return;
  }

  vector<uint8_t> bitstream;
  bool found_marker = false;
  uint16_t expected = frame.payloads.begin()->first;
  for (const auto& pkt : frame.payloads) {
    if (pkt.first != expected) {
      return;
    }
    bitstream.insert(bitstream.end(), pkt.second.begin(), pkt.second.end());
    if (pkt.first == frame.marker_seq) {
      found_marker = true;
      break;
    }
    expected++;
  }

  if (!found_marker || bitstream.empty()) {
    return;
  }

  enqueue_frame(timestamp, std::move(bitstream));
  frame_by_ts_.erase(it);
}

void Decoder::try_decode_with_metadata(uint16_t frame_id)
{
  if (!next_expected_frame_valid_) {
    next_expected_frame_valid_ = true;
    next_expected_frame_id_ = frame_id;
  }

  while (next_expected_frame_valid_) {
    uint16_t decode_frame_id = next_expected_frame_id_;
    auto it = frame_by_id_.find(next_expected_frame_id_);
    if (it == frame_by_id_.end() || !frame_complete(it->second)) {
      uint16_t recovery_frame_id = 0;
      if (!find_complete_keyframe_ahead(&recovery_frame_id)) {
        return;
      }
      decode_frame_id = recovery_frame_id;
      it = frame_by_id_.find(decode_frame_id);
      if (it == frame_by_id_.end() || !frame_complete(it->second)) {
        return;
      }
    }

    const FrameAssembly& frame = it->second;
    vector<uint8_t> bitstream;
    for (uint16_t frag_id = 0; frag_id < frame.frag_cnt; frag_id++) {
      const auto frag_it = frame.fragments.find(frag_id);
      bitstream.insert(bitstream.end(), frag_it->second.begin(), frag_it->second.end());
    }
    if (bitstream.empty()) {
      frame_by_id_.erase(it);
      next_expected_frame_id_ = static_cast<uint16_t>(decode_frame_id + 1);
      cleanup_metadata_frames_before(next_expected_frame_id_);
      continue;
    }

    enqueue_frame(decode_frame_id, std::move(bitstream));

    frame_by_id_.erase(it);
    next_expected_frame_id_ = static_cast<uint16_t>(decode_frame_id + 1);
    cleanup_metadata_frames_before(next_expected_frame_id_);
  }
}

void Decoder::enqueue_frame(uint32_t timestamp, std::vector<uint8_t>&& bitstream)
{
  {
    std::lock_guard<std::mutex> lock(queue_mutex_);
    decode_queue_.emplace_back();
    decode_queue_.back().timestamp = timestamp;
    decode_queue_.back().bitstream = std::move(bitstream);
  }
  queue_cv_.notify_one();
}

void Decoder::worker_main()
{
  const unsigned int hw_threads = std::thread::hardware_concurrency();
  const unsigned int decoder_threads = std::max(1u, std::min(hw_threads, 4u));

  vpx_codec_dec_cfg_t cfg {};
  cfg.threads = decoder_threads;
  cfg.w = width_;
  cfg.h = height_;

  vpx_codec_ctx_t ctx {};
  if (vpx_codec_dec_init(&ctx, &vpx_codec_vp9_dx_algo, &cfg, 0) != VPX_CODEC_OK) {
    cerr << "vpx_codec_dec_init failed in worker thread" << endl;
    return;
  }

  std::unique_ptr<VideoDisplay> display;
  if (render_video_) {
    display.reset(new VideoDisplay(width_, height_));
  }

  std::deque<QueuedFrame> local_queue;
  for (;;) {
    {
      std::unique_lock<std::mutex> lock(queue_mutex_);
      queue_cv_.wait(lock, [this] {
        return stop_worker_ || !decode_queue_.empty();
      });

      if (stop_worker_ && decode_queue_.empty()) {
        break;
      }

      while (!decode_queue_.empty()) {
        local_queue.push_back(std::move(decode_queue_.front()));
        decode_queue_.pop_front();
      }
    }

    while (!local_queue.empty()) {
      if (display && display->signal_quit()) {
        display.reset();
      }

      QueuedFrame frame = std::move(local_queue.front());
      local_queue.pop_front();

      if (vpx_codec_decode(&ctx, frame.bitstream.data(), frame.bitstream.size(), nullptr, 0) == VPX_CODEC_OK) {
        write_decoded_frames(ctx, display.get());
      } else {
        cerr << "VP9 decode failed for timestamp " << frame.timestamp << endl;
      }
    }
  }

  if (vpx_codec_destroy(&ctx) != VPX_CODEC_OK) {
    cerr << "vpx_codec_destroy failed in worker thread" << endl;
  }
}

void Decoder::write_decoded_frames(vpx_codec_ctx_t& ctx, VideoDisplay* display)
{
  vpx_codec_iter_t iter = nullptr;
  vpx_image_t* img = nullptr;
  while ((img = vpx_codec_get_frame(&ctx, &iter)) != nullptr) {
    if (output_) {
      fwrite("FRAME\n", 1, 6, output_);
      write_plane(img->planes[0], img->stride[0], width_, height_);
      write_plane(img->planes[1], img->stride[1], width_ / 2, height_ / 2);
      write_plane(img->planes[2], img->stride[2], width_ / 2, height_ / 2);
    }

    if (display) {
      display->show_frame(RawImage(img));
    }
  }
}

void Decoder::write_plane(uint8_t* plane, int stride, int w, int h)
{
  for (int y = 0; y < h; y++) {
    fwrite(plane + y * stride, 1, w, output_);
  }
}

void Decoder::cleanup_old_frames()
{
  while (frame_by_ts_.size() > 24) {
    frame_by_ts_.erase(frame_by_ts_.begin());
  }

  if (next_expected_frame_valid_) {
    cleanup_metadata_frames_before(next_expected_frame_id_);
  }
}

bool Decoder::frame_complete(const FrameAssembly& frame) const
{
  if (frame.frag_cnt == 0 || frame.fragments.size() < frame.frag_cnt) {
    return false;
  }

  for (uint16_t frag_id = 0; frag_id < frame.frag_cnt; frag_id++) {
    if (frame.fragments.find(frag_id) == frame.fragments.end()) {
      return false;
    }
  }

  return true;
}

bool Decoder::find_complete_keyframe_ahead(uint16_t* frame_id) const
{
  bool found = false;
  int16_t best_diff = 0;
  uint16_t best_id = 0;

  for (const auto& it : frame_by_id_) {
    const uint16_t candidate_id = it.first;
    const FrameAssembly& candidate = it.second;

    if (!frame_id_ahead(candidate_id, next_expected_frame_id_)) {
      continue;
    }
    if (!candidate.is_keyframe || !frame_complete(candidate)) {
      continue;
    }

    const int16_t diff = static_cast<int16_t>(candidate_id - next_expected_frame_id_);
    if (!found || diff > best_diff) {
      found = true;
      best_diff = diff;
      best_id = candidate_id;
    }
  }

  if (!found) {
    return false;
  }

  *frame_id = best_id;
  return true;
}

void Decoder::cleanup_metadata_frames_before(uint16_t frame_id)
{
  for (auto it = frame_by_id_.begin(); it != frame_by_id_.end();) {
    if (it->first == frame_id || frame_id_ahead(it->first, frame_id)) {
      ++it;
      continue;
    }
    it = frame_by_id_.erase(it);
  }
}

} // namespace bwvideo
