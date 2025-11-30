# Encoder Configuration & Usage Comparison: SCReAM BW Tool vs Ringmaster

## Executive Summary
There are **critical differences** in both encoder configuration and usage patterns that could significantly affect your SCReAM comparison results.

---

## 1. ENCODER CONFIGURATION DIFFERENCES

### A. Threading & CPU Usage

| Parameter | SCReAM BW Tool | Ringmaster | Impact |
|-----------|---------------|------------|---------|
| **g_threads** | Not set (default: 1) | **4 threads** | ⚠️ **HIGH** - Ringmaster can encode faster |
| **VP8E_SET_CPUUSED** | **4** (fixed) | **min(get_nprocs(), 16)** (dynamic) | ⚠️ **HIGH** - Variable encoding speed/quality |

**Issue**: Ringmaster uses 4 encoder threads and dynamic CPU usage (up to 16), while BW tool uses single-threaded encoding with fixed CPU=4. This means:
- Ringmaster encodes **faster** (parallel encoding)
- Ringmaster may produce **different quality** at same bitrate
- **Recommendation**: Set `cfg_.g_threads = 4` in scream/code/Encoder.cpp

---

### B. Quantizer (QP) Range

| Parameter | SCReAM BW Tool | Ringmaster | Impact |
|-----------|---------------|------------|---------|
| **rc_min_quantizer** | **4** | **2** | ⚠️ **MEDIUM** - Different quality floor |
| **rc_max_quantizer** | **63** | **52** | ⚠️ **HIGH** - Different quality ceiling |

**Issue**: 
- Ringmaster allows **higher quality** (QP=2 vs 4 minimum)
- Ringmaster is **more restricted** at low quality (QP=52 vs 63 maximum)
- This affects how encoder reacts to bandwidth changes:
  - BW tool can drop quality more (QP up to 63) under congestion
  - Ringmaster maintains higher minimum quality (QP min=2)

**Recommendation**: Match quantizer ranges:
```cpp
impl_->cfg.rc_min_quantizer = 2;  // Change from 4 to 2
impl_->cfg.rc_max_quantizer = 52; // Change from 63 to 52
```

---

### C. Keyframe Control

| Parameter | SCReAM BW Tool | Ringmaster | Impact |
|-----------|---------------|------------|---------|
| **kf_mode** | Not set (auto keyframes) | **VPX_KF_DISABLED** | ⚠️ **CRITICAL** |
| **kf_max_dist** | Not set (~9999 frames) | **UINT_MAX** (disabled) | ⚠️ **CRITICAL** |

**Issue**: 
- BW tool allows **automatic keyframes** by libvpx
- Ringmaster **disables automatic keyframes** completely
- This has **massive impact** on:
  - Recovery from packet loss (auto keyframes help recovery)
  - Bitrate spikes (keyframes are large)
  - SCReAM's congestion window behavior

**Recommendation**: Add to scream/code/Encoder.cpp:
```cpp
impl_->cfg.kf_mode = VPX_KF_DISABLED;
impl_->cfg.kf_max_dist = std::numeric_limits<unsigned int>::max();
impl_->cfg.kf_min_dist = 0;
```

---

### D. Advanced Features (Already Matched ✓)

These are **identical** in both systems:
- ✓ `g_error_resilient = VPX_ERROR_RESILIENT_DEFAULT`
- ✓ `rc_buf_initial_sz/optimal_sz/rc_buf_sz = 500/600/1000`
- ✓ `rc_undershoot_pct/rc_overshoot_pct = 50/50`
- ✓ `VP8E_SET_MAX_INTRA_BITRATE_PCT = 900`
- ✓ `VP9E_SET_TILE_COLUMNS = 2`
- ✓ `VP9E_SET_ROW_MT = 1`
- ✓ `VP9E_SET_AQ_MODE = 3`
- ✓ `VP8E_SET_STATIC_THRESHOLD = 1`
- ✓ `VP9E_SET_NOISE_SENSITIVITY = 1`
- ✓ `VP9E_SET_FRAME_PARALLEL_DECODING = 0`

---

## 2. ENCODER INVOCATION SEQUENCE

### A. When Encoder is Called

**SCReAM BW Tool (scream_sender.cpp):**
```
Timer fires (frame interval)
  ↓
Get SCReAM target bitrate
  ↓
Update encoder bitrate → setBitrate(target_kbps)
  ↓
Read Y4M frame from file
  ↓
Encode frame → encodeFrame(frame_buf)
  ↓
Packetize into RTP (inline in same function)
  ↓
Add to RTP queue
```

**Ringmaster (video_sender.cc):**
```
Timer fires (frame interval)
  ↓
Read Y4M frame from file
  ↓
Get SCReAM target bitrate
  ↓
Update encoder bitrate → set_target_bitrate(kbps)
  ↓
Encode frame → compress_frame(raw_img)
  ├─ encode_frame() - VP9 encoding
  └─ packetize_encoded_frame() - Fragment into datagrams
  ↓
Add to datagram queue
```

### B. Key Difference: Bitrate Update Timing

| System | Bitrate Update | Impact |
|--------|---------------|---------|
| **BW Tool** | **Before** reading frame | Updates take effect on current frame |
| **Ringmaster** | **After** reading frame, **before** encoding | Same: updates take effect on current frame |

✓ **Both systems update bitrate before encoding** - This is **correct and matched**.

---

### C. Key Difference: Frame Reading vs Encoding

**BW Tool:**
- Reads frame in `createRtpThread` (periodic timer loop)
- Encodes **immediately** after reading
- Simple synchronous flow

**Ringmaster:**
- Reads frame in timer callback (event-driven)
- Encodes **immediately** after reading
- More complex event loop but **functionally equivalent**

✓ **Timing is matched** - both encode immediately after reading frame.

---

### D. Key Difference: RTP Packetization

**BW Tool:**
- Manual RTP packetization inline
- Creates RTP packets directly in loop
- Uses `writeRtp()` helper

**Ringmaster:**
- Structured `packetize_encoded_frame()` function
- Creates Datagram objects
- More sophisticated fragmentation logic with SCReAM notification

⚠️ **Minor difference** but shouldn't affect encoder behavior (only affects network layer).

---

## 3. CRITICAL FIXES NEEDED

To ensure **fair comparison**, apply these changes to `scream/code/Encoder.cpp`:

### Fix 1: Match Threading
```cpp
impl_->cfg.g_threads = 4; // Add after g_lag_in_frames
```

### Fix 2: Match CPU Usage
```cpp
// Change from fixed 4 to dynamic like ringmaster
const unsigned int cpu_used = std::min(4, std::max(1, (int)std::thread::hardware_concurrency()));
vpx_codec_control(&impl_->ctx, VP8E_SET_CPUUSED, cpu_used);
```

### Fix 3: Match Quantizer Range
```cpp
impl_->cfg.rc_min_quantizer = 2;  // Change from 4
impl_->cfg.rc_max_quantizer = 52; // Change from 63
```

### Fix 4: Disable Automatic Keyframes (CRITICAL)
```cpp
// Add after rc_overshoot_pct line:
impl_->cfg.kf_mode = VPX_KF_DISABLED;
impl_->cfg.kf_max_dist = std::numeric_limits<unsigned int>::max();
impl_->cfg.kf_min_dist = 0;
```

### Fix 5: Missing rc_resize_allowed and rc_dropframe_thresh
```cpp
// Add after g_threads:
impl_->cfg.rc_resize_allowed = 0;
impl_->cfg.rc_dropframe_thresh = 0;
```

---

## 4. IMPACT ASSESSMENT

| Issue | Impact on SCReAM Comparison | Severity |
|-------|----------------------------|----------|
| **Keyframe mode mismatch** | BW tool has periodic auto keyframes → different loss recovery → unfair congestion window behavior | 🔴 **CRITICAL** |
| **QP max mismatch (63 vs 52)** | BW tool can drop quality lower → appears more "adaptive" to congestion | 🟠 **HIGH** |
| **Threading mismatch (1 vs 4)** | BW tool encodes slower → more queuing delay → affects RTT and CWND | 🟠 **HIGH** |
| **CPU usage mismatch (fixed vs dynamic)** | Variable encoding speed affects pacing and queue dynamics | 🟡 **MEDIUM** |
| **QP min mismatch (4 vs 2)** | Small quality difference at high bitrate | 🟢 **LOW** |

---

## 5. RECOMMENDATIONS

### For Fair Comparison:
1. ✅ **Apply all 5 fixes above to scream/code/Encoder.cpp**
2. ✅ **Rebuild**: `cd /home/nawel/projects/scream && cmake --build .`
3. ✅ **Re-run batch tests** with matched encoder
4. ✅ **Compare results** - now on equal footing

### For Documentation:
- Note in your results that encoder configurations were harmonized
- Mention which parameters were changed and why
- Consider running A/B test: current config vs matched config

---

## 6. SUMMARY TABLE

| Encoder Parameter | BW Tool (Original) | Ringmaster | Recommended BW Tool Fix |
|-------------------|-------------------|------------|------------------------|
| g_threads | 1 (default) | 4 | **4** |
| VP8E_SET_CPUUSED | 4 | dynamic (up to 16) | **dynamic or 4** |
| rc_min_quantizer | 4 | 2 | **2** |
| rc_max_quantizer | 63 | 52 | **52** |
| kf_mode | auto | VPX_KF_DISABLED | **VPX_KF_DISABLED** |
| kf_max_dist | ~9999 | UINT_MAX | **UINT_MAX** |
| rc_resize_allowed | default | 0 | **0** |
| rc_dropframe_thresh | default | 0 | **0** |

**All other parameters are already matched ✓**
