#include "Decoder.h"

#include <iostream>
#include <stdexcept>

#include "image.hh"
#include "sdl.hh"

using namespace std;

namespace bwvideo {

Decoder::Decoder(uint16_t width,
                 uint16_t height,
                 bool render_video,
                 const std::string& output_path)
  : width_(width), height_(height), render_video_(render_video)
{
  vpx_codec_dec_cfg_t cfg {};
  cfg.threads = 4;
  cfg.w = width_;
  cfg.h = height_;
  if (vpx_codec_dec_init(&ctx_, &vpx_codec_vp9_dx_algo, &cfg, 0) != VPX_CODEC_OK) {
    throw runtime_error("vpx_codec_dec_init failed");
  }

  output_ = fopen(output_path.c_str(), "wb");
  if (output_) {
    fprintf(output_, "YUV4MPEG2 W%d H%d F30:1 Ip A0:0 C420\n", width_, height_);
  }

  if (render_video_) {
    display_ = new VideoDisplay(width_, height_);
  }
}

Decoder::~Decoder()
{
  delete display_;
  display_ = nullptr;

  if (output_) {
    fclose(output_);
    output_ = nullptr;
  }

  vpx_codec_destroy(&ctx_);
}

void Decoder::add_rtp_payload(uint16_t seq_nr,
                              uint32_t timestamp,
                              const uint8_t* payload,
                              size_t payload_size,
                              bool marker)
{
  auto& frame = frame_by_ts_[timestamp];
  frame.payloads[seq_nr] = vector<uint8_t>(payload, payload + payload_size);
  if (marker) {
    frame.marker_seen = true;
    frame.marker_seq = seq_nr;
  }

  try_decode(timestamp);
  cleanup_old_frames();
}

void Decoder::try_decode(uint32_t timestamp)
{
  auto it = frame_by_ts_.find(timestamp);
  if (it == frame_by_ts_.end()) {
    return;
  }

  FrameAssembly& frame = it->second;
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

  if (vpx_codec_decode(&ctx_, bitstream.data(), bitstream.size(), nullptr, 0) == VPX_CODEC_OK) {
    write_decoded_frames();
  } else {
    cerr << "VP9 decode failed for timestamp " << timestamp << endl;
  }

  frame_by_ts_.erase(it);
}

void Decoder::write_decoded_frames()
{
  vpx_codec_iter_t iter = nullptr;
  vpx_image_t* img = nullptr;
  while ((img = vpx_codec_get_frame(&ctx_, &iter)) != nullptr) {
    if (output_) {
      fwrite("FRAME\n", 1, 6, output_);
      write_plane(img->planes[0], img->stride[0], width_, height_);
      write_plane(img->planes[1], img->stride[1], width_ / 2, height_ / 2);
      write_plane(img->planes[2], img->stride[2], width_ / 2, height_ / 2);
    }

    if (display_) {
      display_->show_frame(RawImage(img));
      if (display_->signal_quit()) {
        delete display_;
        display_ = nullptr;
      }
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
}

} // namespace bwvideo
