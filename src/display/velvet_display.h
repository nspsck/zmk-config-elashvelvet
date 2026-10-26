/* SPDX-License-Identifier: MIT */
#ifndef VELVET_DISPLAY_H
#define VELVET_DISPLAY_H

#include <stdbool.h>
#include <stdint.h>

#define VELVET_DISPLAY_WIDTH 160
#define VELVET_DISPLAY_HEIGHT 68
#define VELVET_DISPLAY_STRIDE (VELVET_DISPLAY_WIDTH / 8)
#define VELVET_DISPLAY_BUFFER_SIZE (VELVET_DISPLAY_STRIDE * VELVET_DISPLAY_HEIGHT)
#define VELVET_DISPLAY_LAYER_NAME_SIZE 14

enum velvet_pointer_mode {
    VELVET_POINTER_NORMAL,
    VELVET_POINTER_SCROLL,
    VELVET_POINTER_PRECISE,
};

enum velvet_transport {
    VELVET_TRANSPORT_NONE,
    VELVET_TRANSPORT_BLE,
    VELVET_TRANSPORT_USB,
};

struct velvet_display_state {
    bool central;             /* Right half is the central. */
    bool connected;           /* Host on right, split link on left. */
    bool battery_available;
    bool usb_powered;
    uint8_t battery_percent;  /* Clamped to 100 by the renderer. */
    uint8_t ble_profile;      /* Zero-based; shown as BT1..BT5. */
    enum velvet_transport transport;
    enum velvet_pointer_mode pointer_mode;
    char layer_name[VELVET_DISPLAY_LAYER_NAME_SIZE];
};

/* Portable pure-C renderer. MSB-first, row-major, bit 1 = physically white.
 * Does not allocate or reference Zephyr/LVGL. The output is always 160x68. */
void velvet_display_render(uint8_t pixels[VELVET_DISPLAY_BUFFER_SIZE],
                           const struct velvet_display_state *state, uint8_t frame);

/* Four art states: calm, blink, tail sway, wave; calm is held longer. */
uint8_t velvet_display_animation_frame(uint32_t active_ms);

/* Match the trackball listener's priority when both mode keys are held. */
enum velvet_pointer_mode velvet_display_pointer_mode(bool scroll, bool precision);

#endif
