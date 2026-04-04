#ifndef DISPLAY_HH
#define DISPLAY_HH

extern "C" {
#include <SDL2/SDL.h>
}

#include <memory>
#include "image.hh"

class VideoDisplay
{
public:
  VideoDisplay(const uint16_t display_width, const uint16_t display_height);
  ~VideoDisplay();

  void show_frame(const RawImage& raw_img);
  bool signal_quit();

  VideoDisplay(const VideoDisplay& other) = delete;
  const VideoDisplay& operator=(const VideoDisplay& other) = delete;
  VideoDisplay(VideoDisplay&& other) = delete;
  VideoDisplay& operator=(VideoDisplay&& other) = delete;

private:
  uint16_t display_width_;
  uint16_t display_height_;

  SDL_Window* window_ {nullptr};
  SDL_Renderer* renderer_ {nullptr};
  SDL_Texture* texture_ {nullptr};
  std::unique_ptr<SDL_Event> event_ {nullptr};
};

#endif /* DISPLAY_HH */
