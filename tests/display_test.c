/* Host checks for the exact renderer linked into the firmware. */
#include "velvet_display.h"
#include "dragon_assets.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static void snapshot(const char *directory, const char *name,
                     const struct velvet_display_state *state, uint8_t frame) {
    uint8_t pixels[VELVET_DISPLAY_BUFFER_SIZE];
    velvet_display_render(pixels, state, frame);
    char path[1024];
    assert(snprintf(path, sizeof(path), "%s/%s.pbm", directory, name) < (int)sizeof(path));
    FILE *output = fopen(path, "wb");
    assert(output);
    fprintf(output, "P4\n160 68\n");
    /* PBM uses 1=black; the renderer uses 1=physically white. */
    for (size_t i = 0; i < sizeof(pixels); i++) { fputc(pixels[i] ^ 0xff, output); }
    assert(fclose(output) == 0);
}

int main(int argc, char **argv) {
    assert(argc == 2);
    _Static_assert(VELVET_DISPLAY_WIDTH == 160 && VELVET_DISPLAY_HEIGHT == 68,
                   "The installed displays are horizontal");
    _Static_assert(VELVET_DRAGON_FRAME_BYTES * VELVET_DRAGON_FRAME_COUNT == 1664,
                   "Sprite storage budget changed");
    struct velvet_display_state state = {
        .central = true, .connected = true, .battery_available = true,
        .battery_percent = 76, .ble_profile = 0,
        .transport = VELVET_TRANSPORT_BLE, .pointer_mode = VELVET_POINTER_NORMAL,
        .layer_name = "CMKDH",
    };
    struct {
        uint8_t before[16];
        uint8_t pixels[VELVET_DISPLAY_BUFFER_SIZE];
        uint8_t after[16];
    } guarded;
    /* Exercise both halves, full-length unterminated Studio names, all battery
     * values, invalid frame values, and both pointer-mode keys held together. */
    for (unsigned n = 0; n < 256; n++) {
        memset(&guarded, 0xa5, sizeof(guarded));
        state.central = n & 1u;
        state.connected = n & 2u;
        state.battery_available = n & 4u;
        state.usb_powered = n & 8u;
        state.battery_percent = (uint8_t)n;
        state.ble_profile = (uint8_t)n;
        state.transport = (enum velvet_transport)(n % 4);
        state.pointer_mode = velvet_display_pointer_mode(n & 16u, n & 32u);
        memset(state.layer_name, 'W', sizeof(state.layer_name));
        velvet_display_render(guarded.pixels, &state, (uint8_t)n);
        for (unsigned i = 0; i < 16; i++) {
            assert(guarded.before[i] == 0xa5 && guarded.after[i] == 0xa5);
        }
    }
    assert(velvet_display_pointer_mode(false, false) == VELVET_POINTER_NORMAL);
    assert(velvet_display_pointer_mode(false, true) == VELVET_POINTER_PRECISE);
    assert(velvet_display_pointer_mode(true, false) == VELVET_POINTER_SCROLL);
    assert(velvet_display_pointer_mode(true, true) == VELVET_POINTER_SCROLL);
    unsigned seen = 0;
    for (uint32_t ms = 0; ms < 9600; ms += 200) {
        const uint8_t frame = velvet_display_animation_frame(ms);
        assert(frame < VELVET_DRAGON_FRAME_COUNT);
        seen |= 1u << frame;
    }
    assert(seen == 15u);

    state = (struct velvet_display_state){
        .central = true, .connected = true, .battery_available = true,
        .battery_percent = 100, .transport = VELVET_TRANSPORT_BLE,
        .layer_name = "CMKDH",
    };
    uint8_t full[VELVET_DISPLAY_BUFFER_SIZE], over[VELVET_DISPLAY_BUFFER_SIZE];
    velvet_display_render(full, &state, 0);
    state.battery_percent = 255;
    velvet_display_render(over, &state, 0);
    assert(memcmp(full, over, sizeof(full)) == 0);
    state.battery_percent = 76;
    for (unsigned frame = 0; frame < VELVET_DRAGON_FRAME_COUNT; frame++) {
        char name[32];
        state.central = true;
        state.battery_percent = 76;
        snprintf(name, sizeof(name), "right-%u", frame);
        snapshot(argv[1], name, &state, frame);
        state.central = false;
        state.battery_percent = 82;
        snprintf(name, sizeof(name), "left-%u", frame);
        snapshot(argv[1], name, &state, frame);
        for (unsigned other = 0; other < frame; other++) {
            assert(memcmp(velvet_dragon_frames[frame], velvet_dragon_frames[other],
                          VELVET_DRAGON_FRAME_BYTES) != 0);
        }
    }
    state.central = true;
    state.battery_percent = 76;
    state.pointer_mode = VELVET_POINTER_SCROLL;
    snapshot(argv[1], "right-scroll", &state, 0);
    state.pointer_mode = VELVET_POINTER_PRECISE;
    snapshot(argv[1], "right-precision", &state, 0);
    state.pointer_mode = VELVET_POINTER_NORMAL;
    state.transport = VELVET_TRANSPORT_USB;
    state.usb_powered = true;
    strcpy(state.layer_name, "SYMNUM");
    snapshot(argv[1], "right-usb", &state, 0);
    state.central = false;
    state.connected = false;
    state.battery_available = false;
    snapshot(argv[1], "left-disconnected", &state, 0);
    puts("Display checks passed: bounds, native geometry, modes, animation, battery and both halves");
    return 0;
}
