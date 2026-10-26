/* SPDX-License-Identifier: MIT */
#include <lvgl.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/util.h>
#include <zmk/activity.h>
#include <zmk/display/status_screen.h>

#include "velvet_display.h"
#include "velvet-layers.h"

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

/* Each span must be consumed immediately, so a whole frame cannot accumulate
 * draw-task allocations in the 8 KiB pool. ZMK owns the single display queue. */
BUILD_ASSERT(LV_USE_OS == LV_OS_NONE, "Velvet display requires synchronous LVGL drawing");
BUILD_ASSERT(LV_USE_DRAW_SW && LV_DRAW_SW_DRAW_UNIT_CNT == 1,
             "Velvet display requires one software draw unit");

#if IS_ENABLED(CONFIG_ZMK_BATTERY_REPORTING)
#include <zmk/battery.h>
#endif
#if IS_ENABLED(CONFIG_USB_DEVICE_STACK)
#include <zmk/usb.h>
#endif
#if IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
#include <zmk/ble.h>
#include <zmk/endpoints.h>
#include <zmk/keymap.h>
#elif IS_ENABLED(CONFIG_ZMK_SPLIT_BLE)
#include <zmk/split/bluetooth/peripheral.h>
#endif

/* One packed framebuffer; fonts and four sprite frames stay in flash. There
 * is no image decoder, RGB framebuffer, canvas rotation, or per-frame object
 * creation. Draw callbacks and the timer run on ZMK's existing display queue. */
static uint8_t pixels[VELVET_DISPLAY_BUFFER_SIZE];
static lv_obj_t *screen;
static struct velvet_display_state previous_state;
static uint8_t previous_frame;
static bool have_state;
static uint32_t active_ms;
static uint32_t last_tick;

#if IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
static zmk_keymap_layer_id_t typing_layer(void) {
    /* Scan in live Studio order, but display pointer modes separately. */
    for (int index = ZMK_KEYMAP_LAYERS_LEN - 1; index >= 0; index--) {
        const zmk_keymap_layer_id_t id = zmk_keymap_layer_index_to_id(index);
        if (id == ZMK_KEYMAP_LAYER_ID_INVAL || id == VELVET_LAYER_SCROLL ||
            id == VELVET_LAYER_PRECISION) {
            continue;
        }
        if (zmk_keymap_layer_active(id)) {
            return id;
        }
    }
    return VELVET_LAYER_CMKDH;
}
#endif

static void read_state(struct velvet_display_state *state) {
    memset(state, 0, sizeof(*state));
    state->central = IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL);
#if IS_ENABLED(CONFIG_ZMK_BATTERY_REPORTING)
    state->battery_available = true;
    state->battery_percent = zmk_battery_state_of_charge();
#endif
#if IS_ENABLED(CONFIG_USB_DEVICE_STACK)
    state->usb_powered = zmk_usb_is_powered();
#endif

#if IS_ENABLED(CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
    const struct zmk_endpoint_instance endpoint = zmk_endpoint_get_selected();
    if (endpoint.transport == ZMK_TRANSPORT_USB) {
        state->transport = VELVET_TRANSPORT_USB;
#if IS_ENABLED(CONFIG_USB_DEVICE_STACK)
        state->connected = zmk_usb_is_hid_ready();
#endif
    } else {
#if IS_ENABLED(CONFIG_ZMK_BLE)
        /* Keep the selected BLE slot visible while advertising/disconnected. */
        state->transport = VELVET_TRANSPORT_BLE;
        state->ble_profile = zmk_ble_active_profile_index();
        state->connected = zmk_ble_active_profile_is_connected();
#endif
    }
    state->pointer_mode = velvet_display_pointer_mode(
        zmk_keymap_layer_active(VELVET_LAYER_SCROLL),
        zmk_keymap_layer_active(VELVET_LAYER_PRECISION));
    const zmk_keymap_layer_id_t layer = typing_layer();
    const char *name = zmk_keymap_layer_name(layer);
    if (name && name[0]) {
        snprintf(state->layer_name, sizeof(state->layer_name), "%s", name);
    } else {
        snprintf(state->layer_name, sizeof(state->layer_name), "LAYER %u", (unsigned)layer);
    }
#elif IS_ENABLED(CONFIG_ZMK_SPLIT_BLE)
    state->connected = zmk_split_bt_peripheral_is_connected();
#endif
}

static bool lit(int x, int y) {
    return (pixels[y * VELVET_DISPLAY_STRIDE + x / 8] & (0x80u >> (x % 8))) != 0;
}

static void draw_screen(lv_event_t *event) {
    lv_layer_t *layer = lv_event_get_layer(event);
    lv_draw_rect_dsc_t ink;
    lv_draw_rect_dsc_init(&ink);
    /* Sharp nice!view polarity: nominal LVGL white is physically black, and
     * nominal black is physically white. Match the stock non-inverted theme. */
    ink.bg_color = lv_color_black();
    ink.bg_opa = LV_OPA_COVER;
    for (int y = 0; y < VELVET_DISPLAY_HEIGHT; y++) {
        for (int x = 0; x < VELVET_DISPLAY_WIDTH;) {
            if (!lit(x, y)) {
                x++;
                continue;
            }
            const int first = x;
            do { x++; } while (x < VELVET_DISPLAY_WIDTH && lit(x, y));
            const lv_area_t span = {.x1 = first, .y1 = y, .x2 = x - 1, .y2 = y};
            lv_draw_rect(layer, &ink, &span);
        }
    }
}

static void refresh(lv_timer_t *timer) {
    (void)timer;
    const uint32_t now = lv_tick_get();
    const uint32_t elapsed = now - last_tick;
    last_tick = now;
    if (zmk_activity_get_state() != ZMK_ACTIVITY_ACTIVE) {
        return;
    }
    /* ZMK stops display ticks while blanked. Do not fast-forward the animation
     * across sleep, even when no callback ran to record the idle transition. */
    active_ms += elapsed > 200u ? 200u : elapsed;
    struct velvet_display_state state;
    read_state(&state);
    const uint8_t frame = velvet_display_animation_frame(active_ms);
    if (!have_state || previous_frame != frame ||
        memcmp(&state, &previous_state, sizeof(state)) != 0) {
        velvet_display_render(pixels, &state, frame);
        previous_state = state;
        previous_frame = frame;
        have_state = true;
        lv_obj_invalidate(screen);
    }
}

lv_obj_t *zmk_display_status_screen(void) {
    if (screen) {
        return screen;
    }
    screen = lv_obj_create(NULL);
    if (!screen) {
        return NULL;
    }
    lv_obj_remove_style_all(screen);
    lv_obj_remove_flag(screen, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_size(screen, VELVET_DISPLAY_WIDTH, VELVET_DISPLAY_HEIGHT);
    lv_obj_set_style_bg_color(screen, lv_color_white(), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_add_event_cb(screen, draw_screen, LV_EVENT_DRAW_MAIN, NULL);
    read_state(&previous_state);
    velvet_display_render(pixels, &previous_state, 0);
    have_state = true;
    last_tick = lv_tick_get();
    if (!lv_timer_create(refresh, 200, NULL)) {
        LOG_ERR("Velvet display timer allocation failed");
    }
    return screen;
}
