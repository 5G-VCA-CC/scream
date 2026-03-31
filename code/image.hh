#ifndef IMAGE_HH
#define IMAGE_HH

extern "C" {
#include <vpx/vpx_image.h>
}

#include <cstdint>
#include <string>

class RawImage
{
public:
  RawImage(const uint16_t display_width, const uint16_t display_height);
  RawImage(vpx_image_t* const vpx_img);
  ~RawImage();

  vpx_image* get_vpx_image() const { return vpx_img_; }
  uint16_t display_width() const { return display_width_; }
  uint16_t display_height() const { return display_height_; }

  size_t y_size() const { return display_width_ * display_height_; }
  size_t uv_size() const { return display_width_ * display_height_ / 4; }

  uint8_t* y_plane() const { return vpx_img_->planes[VPX_PLANE_Y]; }
  uint8_t* u_plane() const { return vpx_img_->planes[VPX_PLANE_U]; }
  uint8_t* v_plane() const { return vpx_img_->planes[VPX_PLANE_V]; }

  int y_stride() const { return vpx_img_->stride[VPX_PLANE_Y]; }
  int u_stride() const { return vpx_img_->stride[VPX_PLANE_U]; }
  int v_stride() const { return vpx_img_->stride[VPX_PLANE_V]; }

  void copy_from_yuyv(const std::string& src);
  void copy_y_from(const std::string& src);
  void copy_u_from(const std::string& src);
  void copy_v_from(const std::string& src);

  RawImage(const RawImage& other) = delete;
  const RawImage& operator=(const RawImage& other) = delete;
  RawImage(RawImage&& other) = delete;
  RawImage& operator=(RawImage&& other) = delete;

private:
  vpx_image* vpx_img_;
  bool own_vpx_img_;
  uint16_t display_width_;
  uint16_t display_height_;
};

#endif /* IMAGE_HH */
