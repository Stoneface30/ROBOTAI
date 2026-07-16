// Shared eye renderer for both GC9A01A displays.
// States: 0 idle, 1 listening, 2 thinking/glance-up, 3 speaking, 4 error,
//         5 sleepy, 6 laundry-spin, 7 dance, 8 silly.
// timer_prog > 0 draws a countdown ring on top of any state.
// Iris ring color follows HA weather (set via weather text_sensor).
// Seasonal: October pumpkin sclera, December snow flecks.
#pragma once
#include "esphome.h"

static inline void draw_robot_eye(esphome::display::Display &it, int state,
                                  bool blinking, int tick, float timer_prog,
                                  int ir, int ig, int ib, int month,
                                  bool right_eye) {
  using esphome::Color;
  const int W = 240, H = 240;
  const int cx = W / 2, cy = H / 2;

  it.fill(Color(0, 0, 0));

  // Blink overrides everything - closed eye = horizontal slit
  if (blinking) {
    it.filled_rectangle(0, cy - 6, W, 12, Color(255, 255, 255));
    return;
  }

  // Sclera - seasonal tint
  Color sclera = Color(255, 255, 255);
  if (state == 4) sclera = Color(255, 60, 60);          // error = red
  else if (month == 10) sclera = Color(255, 170, 60);   // October pumpkin
  it.filled_circle(cx, cy, 110, sclera);

  // December snow flecks (deterministic pseudo-random, drifting with tick)
  if (month == 12 && state != 4) {
    for (int i = 0; i < 8; i++) {
      int sx = cx - 90 + ((i * 53 + tick * 2) % 180);
      int sy = cy - 90 + ((i * 97 + tick) % 180);
      if ((sx - cx) * (sx - cx) + (sy - cy) * (sy - cy) < 100 * 100)
        it.filled_circle(sx, sy, 3, Color(200, 225, 255));
    }
  }

  // Pupil size + position per state
  int pupil_r = 38, px = cx, py = cy;
  switch (state) {
    case 1: pupil_r = 52; break;                       // listening - dilated
    case 2: py = cy - 35; pupil_r = 34; break;         // thinking - look up
    case 3: pupil_r = 44; break;                       // speaking
    case 4: pupil_r = 30; break;                       // error - pinprick
    case 5:                                            // sleepy - low, small
      py = cy + 28; pupil_r = 30; break;
    case 6: {                                          // laundry spin - orbit
      float a = tick * 0.35f;
      px = cx + (int)(45 * cosf(a));
      py = cy + (int)(45 * sinf(a));
      pupil_r = 32; break;
    }
    case 7: {                                          // dance - bob to the beat
      py = cy + (int)(18 * sinf(tick * 0.5f));
      px = cx + (int)(8 * sinf(tick * 0.25f));
      pupil_r = 40 + (int)(6 * sinf(tick * 0.5f)); break;
    }
    case 8:                                            // silly - cross-eyed
      px = cx + (right_eye ? -30 : 30);
      py = cy + (int)(10 * sinf(tick * 0.7f));
      pupil_r = 36; break;
    default: break;                                    // idle
  }

  // Weather-tinted iris ring behind the pupil
  it.filled_circle(px, py, pupil_r + 12, Color((uint8_t) ir, (uint8_t) ig, (uint8_t) ib));
  it.filled_circle(px, py, pupil_r, Color(0, 0, 0));

  // Sleepy eyelid droops over the top of the eye
  if (state == 5) {
    int droop = 62 + (int)(8 * sinf(tick * 0.08f));    // slow breathing droop
    it.filled_rectangle(0, 0, W, cy - 110 + droop, Color(0, 0, 0));
  }

  // Catch-light highlight
  it.filled_circle(px + pupil_r / 3, py - pupil_r / 3, 6, Color(255, 255, 255));

  // Countdown ring overlay (voice timers): sweeps clockwise from 12 o'clock
  if (timer_prog > 0.0f && timer_prog < 1.0f) {
    int steps = (int)(timer_prog * 30.0f);
    for (int i = 0; i <= steps; i++) {
      float a = -1.5708f + (i / 30.0f) * 6.2832f;
      int rx = cx + (int)(102 * cosf(a));
      int ry = cy + (int)(102 * sinf(a));
      it.filled_circle(rx, ry, 5, Color(80, 220, 120));
    }
  }
}
