// Eye-pack expression framework for both GC9A01A displays (240x240).
//
// Data-driven: each expression is one row in EYE_EXPRESSIONS (pupil geometry,
// animation function id, palette override, feature flags). Adding a new
// expression = add one enum entry + one table row (+ optionally one small
// animation function registered in EYE_ANIMS).
//
// States: 0 idle, 1 listening, 2 thinking, 3 speaking, 4 error, 5 sleepy,
//         6 laundry-spin, 7 dance, 8 silly, 9 bin-night, 10 watching.
// Overlays that work on top of any state:
//   - blink_amount 0..1  -> top+bottom eyelids close toward the middle
//   - timer_prog 0..1    -> green countdown dot ring sweeping from 12 o'clock
//   - ir/ig/ib           -> weather-tinted iris ring
//   - month              -> seasonal sclera (Oct pumpkin) / snow flecks (Dec)
//
// Panels are mounted rotated 90 deg; ESPHome `rotation:` corrects that, so all
// drawing here is in normal screen coordinates (y = vertical).
// Budget: <= ~50 primitives per frame (10 FPS on shared SPI).
#pragma once
#include "esphome.h"
#include <cmath>

namespace robot_eye {

using esphome::Color;
using esphome::display::Display;

static constexpr int W = 240, H = 240;
static constexpr int CX = 120, CY = 120;
static constexpr int EYE_R = 110;  // sclera radius

// ---------- Expression table ----------------------------------------------

enum : uint8_t {  // animation function ids (indexes into EYE_ANIMS)
  A_NONE = 0, A_ORBIT, A_BOB, A_SILLY, A_PAN,
  A_COUNT
};

enum : uint8_t {  // feature flags
  F_SCLERA_OVERRIDE = 1 << 0,  // use scl_r/g/b instead of default sclera
  F_NO_SEASON       = 1 << 1,  // suppress pumpkin tint + snow flecks
  F_DROOPY_LID      = 1 << 2,  // sleepy breathing eyelid overlay
  F_BIN_ICON        = 1 << 3,  // draw trash bin instead of pupil
  F_NO_CATCHLIGHT   = 1 << 4,  // skip the white highlight dot
};

struct EyeExpression {
  uint8_t pupil_r;             // base pupil radius
  int8_t  px_off, py_off;      // static pupil offset from center
  uint8_t anim;                // A_* id
  uint8_t flags;               // F_* bitmask
  uint8_t scl_r, scl_g, scl_b; // sclera palette override (F_SCLERA_OVERRIDE)
};

static constexpr EyeExpression EYE_EXPRESSIONS[] = {
  /* 0 idle      */ {38, 0,   0, A_NONE,  0, 0, 0, 0},
  /* 1 listening */ {52, 0,   0, A_NONE,  0, 0, 0, 0},   // dilated
  /* 2 thinking  */ {34, 0, -35, A_NONE,  0, 0, 0, 0},   // glance up
  /* 3 speaking  */ {44, 0,   0, A_NONE,  0, 0, 0, 0},
  /* 4 error     */ {30, 0,   0, A_NONE,  F_SCLERA_OVERRIDE | F_NO_SEASON,
                     255, 60, 60},                        // red, pinprick
  /* 5 sleepy    */ {30, 0,  28, A_NONE,  F_DROOPY_LID, 0, 0, 0},
  /* 6 spin      */ {32, 0,   0, A_ORBIT, 0, 0, 0, 0},   // laundry orbit
  /* 7 dance     */ {40, 0,   0, A_BOB,   0, 0, 0, 0},
  /* 8 silly     */ {36, 0,   0, A_SILLY, 0, 0, 0, 0},   // cross-eyed
  /* 9 bin night */ { 0, 0,   0, A_NONE,  F_BIN_ICON | F_NO_CATCHLIGHT,
                     0, 0, 0},
  /* 10 watching */ {38, 0,   0, A_PAN,   0, 0, 0, 0},   // vacuum tracking
};
static constexpr int EYE_STATE_COUNT =
    sizeof(EYE_EXPRESSIONS) / sizeof(EYE_EXPRESSIONS[0]);

// ---------- Animation functions --------------------------------------------
// Each mutates pupil position/radius from continuous time t (seconds).
// Time-based (not tick-based) so both eyes sample the same phase and the
// motion stays smooth regardless of frame scheduling.

typedef void (*EyeAnimFn)(float t, bool right_eye, float &px, float &py, float &pr);

static inline void anim_none(float, bool, float &, float &, float &) {}

static inline void anim_orbit(float t, bool, float &px, float &py, float &) {
  float a = t * 3.5f;
  px += 45.0f * cosf(a);
  py += 45.0f * sinf(a);
}

static inline void anim_bob(float t, bool, float &px, float &py, float &pr) {
  py += 18.0f * sinf(t * 5.0f);
  px += 8.0f * sinf(t * 2.5f);
  pr += 6.0f * sinf(t * 5.0f);
}

static inline void anim_silly(float t, bool right_eye, float &px, float &py, float &) {
  px += right_eye ? -30.0f : 30.0f;  // cross-eyed: both pupils toward the nose
  py += 10.0f * sinf(t * 7.0f);
}

static inline void anim_pan(float t, bool, float &px, float &, float &) {
  px += 55.0f * sinf(t * 1.5708f);   // slow left-right sweep, ~4 s period
}

static const EyeAnimFn EYE_ANIMS[A_COUNT] = {
  anim_none, anim_orbit, anim_bob, anim_silly, anim_pan,
};

// ---------- Feature drawers -------------------------------------------------

// Blink profile from elapsed ms since blink_start: quick close (110 ms),
// brief hold (80 ms), slower open (140 ms). Continuous — sampled per frame.
static inline float blink_profile(uint32_t elapsed_ms) {
  if (elapsed_ms < 110) return elapsed_ms / 110.0f;
  if (elapsed_ms < 190) return 1.0f;
  if (elapsed_ms < 330) return 1.0f - (elapsed_ms - 190) / 140.0f;
  return 0.0f;
}

// Friendly trash bin in place of the pupil (state 9 "bin night").
static inline void draw_bin_icon(Display &it, int tick) {
  const Color body(70, 115, 85);    // calm muted green — chore, not alarm
  const Color lid(95, 150, 110);
  const Color ridge(50, 88, 64);
  // Gentle lid wiggle: bobs up 0..4 px like it's humming to itself.
  int lift = (int) (2.0f + 2.0f * sinf(tick * 0.22f));
  // Body: trapezoid = center rect + two side triangles (narrower at bottom).
  it.filled_rectangle(CX - 24, CY - 16, 48, 52, body);
  it.filled_triangle(CX - 31, CY - 16, CX - 24, CY - 16, CX - 24, CY + 35, body);
  it.filled_triangle(CX + 31, CY - 16, CX + 24, CY - 16, CX + 24, CY + 35, body);
  // Ridges down the body.
  it.line(CX - 12, CY - 8, CX - 12, CY + 28, ridge);
  it.line(CX,      CY - 8, CX,      CY + 28, ridge);
  it.line(CX + 12, CY - 8, CX + 12, CY + 28, ridge);
  // Lid + handle, floating slightly above the body.
  it.filled_rectangle(CX - 34, CY - 26 - lift, 68, 8, lid);
  it.filled_rectangle(CX - 10, CY - 33 - lift, 20, 6, lid);
}

// December snow flecks (deterministic pseudo-random, drifting with tick).
static inline void draw_snow(Display &it, int tick) {
  for (int i = 0; i < 8; i++) {
    int sx = CX - 90 + ((i * 53 + tick * 2) % 180);
    int sy = CY - 90 + ((i * 97 + tick) % 180);
    if ((sx - CX) * (sx - CX) + (sy - CY) * (sy - CY) < 100 * 100)
      it.filled_circle(sx, sy, 3, Color(200, 225, 255));
  }
}

// Countdown ring: green dots sweep clockwise from 12 o'clock.
static inline void draw_timer_ring(Display &it, float prog) {
  int steps = (int) (prog * 30.0f);
  for (int i = 0; i <= steps; i++) {
    float a = -1.5708f + (i / 30.0f) * 6.2832f;
    it.filled_circle(CX + (int) (102.0f * cosf(a)),
                     CY + (int) (102.0f * sinf(a)), 5, Color(80, 220, 120));
  }
}

// Eyelids: black lids close from top AND bottom, meeting in the middle.
// blink_amount 0.0 = fully open, 1.0 = fully closed.
static inline void draw_eyelids(Display &it, float blink_amount) {
  if (blink_amount <= 0.02f) return;
  if (blink_amount > 1.0f) blink_amount = 1.0f;
  const Color black(0, 0, 0);
  int lid = (int) (blink_amount * (EYE_R + 2));       // per-lid travel
  int top_edge = (CY - EYE_R) + lid;                  // bottom of top lid
  int bot_edge = (CY + EYE_R) - lid;                  // top of bottom lid
  it.filled_rectangle(0, 0, W, top_edge, black);
  it.filled_rectangle(0, bot_edge, W, H - bot_edge, black);
  if (blink_amount < 0.98f) {
    // Soft lid-edge lines so mid-blink reads as eyelids, not a glitch.
    const Color edge(70, 58, 50);
    it.line(0, top_edge, W - 1, top_edge, edge);
    it.line(0, bot_edge - 1, W - 1, bot_edge - 1, edge);
  }
}

}  // namespace robot_eye

// ---------- Renderer ---------------------------------------------------------
// Called from both display lambdas in dualeye.yaml every 50 ms (20 FPS).
// now_ms: millis(); blink_start_ms: last blink trigger (0 = never).

static inline void draw_robot_eye(esphome::display::Display &it, int state,
                                  uint32_t now_ms, uint32_t blink_start_ms,
                                  float timer_prog, int ir, int ig, int ib,
                                  int month, bool right_eye) {
  using namespace robot_eye;

  const float t = now_ms / 1000.0f;
  const int tick = (int) (now_ms / 100);   // legacy 10 Hz tick for icon wiggles
  const float blink_amount =
      blink_start_ms ? blink_profile(now_ms - blink_start_ms) : 0.0f;

  it.fill(Color(0, 0, 0));

  // Fully closed: nothing under the lids is worth drawing.
  if (blink_amount >= 0.98f) {
    it.line(0, CY - 1, W - 1, CY - 1, Color(70, 58, 50));  // resting lash line
    return;
  }

  if (state < 0 || state >= EYE_STATE_COUNT) state = 0;
  const EyeExpression &ex = EYE_EXPRESSIONS[state];

  // Sclera: table palette override > seasonal tint > default white.
  Color sclera(255, 255, 255);
  if (ex.flags & F_SCLERA_OVERRIDE)
    sclera = Color(ex.scl_r, ex.scl_g, ex.scl_b);
  else if (month == 10 && !(ex.flags & F_NO_SEASON))
    sclera = Color(255, 170, 60);  // October pumpkin
  it.filled_circle(CX, CY, EYE_R, sclera);

  if (month == 12 && !(ex.flags & F_NO_SEASON)) draw_snow(it, tick);

  if (ex.flags & F_BIN_ICON) {
    draw_bin_icon(it, tick);
  } else {
    // Target pupil geometry: table row + the state's animation function.
    float tx = CX + ex.px_off, ty = CY + ex.py_off, tr = ex.pupil_r;
    EYE_ANIMS[ex.anim](t, right_eye, tx, ty, tr);

    // Exponential smoothing toward the target — state changes glide instead
    // of snapping, and animation motion is softened. Per-eye state ([0]=left,
    // [1]=right; each display lambda runs on the main loop, no races).
    static float sm[2][3] = {{CX, CY, 38.0f}, {CX, CY, 38.0f}};
    float *s = sm[right_eye ? 1 : 0];
    const float alpha = 0.45f;   // ~3 frames to converge at 20 FPS
    s[0] += (tx - s[0]) * alpha;
    s[1] += (ty - s[1]) * alpha;
    s[2] += (tr - s[2]) * alpha;
    int px = (int) s[0], py = (int) s[1], pr = (int) s[2];

    // Weather-tinted iris ring behind the pupil.
    it.filled_circle(px, py, pr + 12, Color((uint8_t) ir, (uint8_t) ig, (uint8_t) ib));
    it.filled_circle(px, py, pr, Color(0, 0, 0));
    if (!(ex.flags & F_NO_CATCHLIGHT))
      it.filled_circle(px + pr / 3, py - pr / 3, 6, Color(255, 255, 255));
  }

  // Sleepy: heavy top lid droops with a slow breathing rhythm.
  if (ex.flags & F_DROOPY_LID) {
    int droop = 62 + (int) (8.0f * sinf(t * 0.8f));
    it.filled_rectangle(0, 0, W, (CY - EYE_R) + droop, Color(0, 0, 0));
  }

  if (timer_prog > 0.0f && timer_prog < 1.0f) draw_timer_ring(it, timer_prog);

  draw_eyelids(it, blink_amount);  // always last — lids cover everything
}
