/* SPDX-License-Identifier: MIT */
#include "velvet_display.h"
#include "dragon_assets.h"

#include <stddef.h>
#include <stdio.h>
#include <string.h>

/* Compact 5x7 bitmap alphabet, stored as five-bit rows. No LVGL font cache. */
static const uint8_t letters[26][7] = {
    {14, 17, 17, 31, 17, 17, 17}, /* A */
    {30, 17, 17, 30, 17, 17, 30}, {14, 17, 16, 16, 16, 17, 14},
    {30, 17, 17, 17, 17, 17, 30}, {31, 16, 16, 30, 16, 16, 31},
    {31, 16, 16, 30, 16, 16, 16}, {14, 17, 16, 23, 17, 17, 15},
    {17, 17, 17, 31, 17, 17, 17}, {14, 4, 4, 4, 4, 4, 14},
    {7, 2, 2, 2, 18, 18, 12}, {17, 18, 20, 24, 20, 18, 17},
    {16, 16, 16, 16, 16, 16, 31}, {17, 27, 21, 21, 17, 17, 17},
    {17, 25, 21, 19, 17, 17, 17}, {14, 17, 17, 17, 17, 17, 14},
    {30, 17, 17, 30, 16, 16, 16}, {14, 17, 17, 17, 21, 18, 13},
    {30, 17, 17, 30, 20, 18, 17}, {15, 16, 16, 14, 1, 1, 30},
    {31, 4, 4, 4, 4, 4, 4}, {17, 17, 17, 17, 17, 17, 14},
    {17, 17, 17, 17, 17, 10, 4}, {17, 17, 17, 21, 21, 21, 10},
    {17, 17, 10, 4, 10, 17, 17}, {17, 17, 10, 4, 4, 4, 4},
    {31, 1, 2, 4, 8, 16, 31},
};
static const uint8_t numbers[10][7] = {
    {14, 17, 19, 21, 25, 17, 14}, {4, 12, 4, 4, 4, 4, 14},
    {14, 17, 1, 2, 4, 8, 31}, {30, 1, 1, 14, 1, 1, 30},
    {2, 6, 10, 18, 31, 2, 2}, {31, 16, 16, 30, 1, 1, 30},
    {14, 16, 16, 30, 17, 17, 14}, {31, 1, 2, 4, 8, 8, 8},
    {14, 17, 17, 14, 17, 17, 14}, {14, 17, 17, 15, 1, 1, 14},
};

static const uint8_t *glyph(char c) {
    static const uint8_t blank[] = {0, 0, 0, 0, 0, 0, 0};
    static const uint8_t percent[] = {25, 25, 2, 4, 8, 19, 19};
    static const uint8_t colon[] = {0, 4, 4, 0, 4, 4, 0};
    static const uint8_t question[] = {14, 17, 1, 2, 4, 0, 4};
    static const uint8_t dash[] = {0, 0, 0, 31, 0, 0, 0};
    static const uint8_t plus[] = {0, 4, 4, 31, 4, 4, 0};
    static const uint8_t slash[] = {1, 1, 2, 4, 8, 16, 16};
    static const uint8_t dot[] = {0, 0, 0, 0, 0, 0, 4};
    static const uint8_t lower_h[] = {16, 16, 22, 25, 17, 17, 17};
    static const uint8_t lower_i[] = {4, 0, 12, 4, 4, 4, 14};

    if (c >= 'A' && c <= 'Z') {
        return letters[c - 'A'];
    }
    if (c >= '0' && c <= '9') {
        return numbers[c - '0'];
    }
    switch (c) {
    case ' ': return blank;
    case '%': return percent;
    case ':': return colon;
    case '-': case '_': return dash;
    case '+': return plus;
    case '/': return slash;
    case '.': return dot;
    case 'h': return lower_h;
    case 'i': return lower_i;
    default: return question;
    }
}

static void pixel(uint8_t *pixels, int x, int y) {
    if (x >= 0 && x < VELVET_DISPLAY_WIDTH && y >= 0 && y < VELVET_DISPLAY_HEIGHT) {
        pixels[y * VELVET_DISPLAY_STRIDE + x / 8] |= (uint8_t)(0x80u >> (x % 8));
    }
}

static void box(uint8_t *pixels, int x, int y, int width, int height) {
    for (int row = 0; row < height; row++) {
        for (int col = 0; col < width; col++) {
            pixel(pixels, x + col, y + row);
        }
    }
}

static void text(uint8_t *pixels, int x, int y, const char *value, int scale) {
    for (; *value && x + 5 * scale <= VELVET_DISPLAY_WIDTH; value++, x += 6 * scale) {
        const uint8_t *shape = glyph(*value);
        for (int row = 0; row < 7; row++) {
            for (int col = 0; col < 5; col++) {
                if (shape[row] & (1u << (4 - col))) {
                    box(pixels, x + col * scale, y + row * scale, scale, scale);
                }
            }
        }
    }
}

static void text_right(uint8_t *pixels, int y, const char *value) {
    text(pixels, VELVET_DISPLAY_WIDTH - 2 - (int)strlen(value) * 6 + 1, y, value, 1);
}

static void heart(uint8_t *pixels, int x, int y, int scale) {
    static const uint8_t shape[] = {0x36, 0x7f, 0x7f, 0x3e, 0x1c, 0x08};
    for (int row = 0; row < 6; row++) {
        for (int col = 0; col < 7; col++) {
            if (shape[row] & (1u << (6 - col))) {
                box(pixels, x + col * scale, y + row * scale, scale, scale);
            }
        }
    }
}

static void dragon(uint8_t *pixels, uint8_t frame) {
    const uint8_t *art = velvet_dragon_frames[frame % VELVET_DRAGON_FRAME_COUNT];
    for (int y = 0; y < VELVET_DRAGON_HEIGHT; y++) {
        for (int x = 0; x < VELVET_DRAGON_WIDTH; x++) {
            if (art[y * (VELVET_DRAGON_WIDTH / 8) + x / 8] & (0x80u >> (x % 8))) {
                pixel(pixels, x + 2, y + 15);
            }
        }
    }
}

enum velvet_pointer_mode velvet_display_pointer_mode(bool scroll, bool precision) {
    return scroll ? VELVET_POINTER_SCROLL
                  : precision ? VELVET_POINTER_PRECISE : VELVET_POINTER_NORMAL;
}

uint8_t velvet_display_animation_frame(uint32_t active_ms) {
    const uint32_t phase = active_ms % 4800u;
    if (phase < 2800u) { return 0; }
    if (phase < 3000u) { return 1; }
    if (phase < 3600u) { return 0; }
    if (phase < 4200u) { return 2; }
    return 3;
}

void velvet_display_render(uint8_t pixels[VELVET_DISPLAY_BUFFER_SIZE],
                           const struct velvet_display_state *state, uint8_t frame) {
    char value[20];
    memset(pixels, 0, VELVET_DISPLAY_BUFFER_SIZE);
    const unsigned battery = state->battery_percent > 100 ? 100 : state->battery_percent;
    if (state->battery_available) {
        snprintf(value, sizeof(value), "%c%u%%", state->central ? 'R' : 'L', battery);
    } else {
        snprintf(value, sizeof(value), "%c--%%", state->central ? 'R' : 'L');
    }
    text(pixels, 2, 3, value, 1);
    /* Own-half battery bar. '+' means USB power present, not charge-current sensing. */
    box(pixels, 38, 3, 14, 1);
    box(pixels, 38, 9, 14, 1);
    box(pixels, 38, 3, 1, 7);
    box(pixels, 51, 3, 1, 7);
    box(pixels, 52, 5, 2, 3);
    if (state->battery_available) {
        box(pixels, 40, 5, (int)((battery * 10u + 50u) / 100u), 3);
    }
    if (state->usb_powered) {
        text(pixels, 58, 3, "+", 1);
    }
    box(pixels, 2, 12, 156, 1);
    dragon(pixels, frame);

    if (state->central) {
        switch (state->transport) {
        case VELVET_TRANSPORT_USB:
            snprintf(value, sizeof(value), "USB%s", state->connected ? "" : " ?");
            break;
        case VELVET_TRANSPORT_BLE:
            snprintf(value, sizeof(value), "BT%u%s", (unsigned)state->ble_profile + 1,
                     state->connected ? "" : " ?");
            break;
        default:
            snprintf(value, sizeof(value), "OFFLINE");
            break;
        }
        text_right(pixels, 3, value);
        text(pixels, 76, 19, "LAYER", 1);
        size_t length = 0;
        while (length < sizeof(state->layer_name) && state->layer_name[length]) {
            char c = state->layer_name[length];
            value[length++] = (c >= 'a' && c <= 'z') ? (char)(c - 'a' + 'A') : c;
        }
        value[length] = '\0';
        if (!length) {
            strcpy(value, "BASE");
            length = 4;
        }
        text(pixels, 76, 31, value, length <= 6 ? 2 : 1);
        box(pixels, 76, 49, 80, 1);
        text(pixels, 76, 55,
             state->pointer_mode == VELVET_POINTER_SCROLL ? "SCROLL"
             : state->pointer_mode == VELVET_POINTER_PRECISE ? "PRECISE" : "POINTER", 1);
    } else {
        text_right(pixels, 3, state->connected ? "LINK OK" : "NO LINK");
        heart(pixels, 83, 20, 2);
        heart(pixels, 138, 23 + ((frame & 1u) ? 1 : 0), 1);
        text(pixels, 86, 39, "hi :3", 2);
        heart(pixels, 118, 59, 1);
    }
}
