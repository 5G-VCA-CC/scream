#ifndef DISPLAY_HH
#define DISPLAY_HH

extern "C" {
#include <SDL2/SDL.h>
}

#include <memory>

class VideoDisplay
{
public:
  VideoDisplay(const uint16_t display_width, const uint16_t display_height);
  ~VideoDisplay();

  // display a frame provided as raw Y, U, V planes
  void show_frame_planes(const uint8_t* y, int y_stride,
                         const uint8_t* u, int u_stride,
                         const uint8_t* v, int v_stride,
                         const uint16_t display_width, const uint16_t display_height);

  // if signaled to quit
  bool signal_quit();

  // forbid copy and move operators
  VideoDisplay(const VideoDisplay & other) = delete;
  const VideoDisplay & operator=(const VideoDisplay & other) = delete;
  VideoDisplay(VideoDisplay && other) = delete;
  VideoDisplay & operator=(VideoDisplay && other) = delete;

private:
  uint16_t display_width_;
  uint16_t display_height_;

  SDL_Window * window_ {nullptr};
  SDL_Renderer * renderer_ {nullptr};
  SDL_Texture * texture_ {nullptr};
  std::unique_ptr<SDL_Event> event_ {nullptr};
};

#endif /* DISPLAY_HH */
