// ff-expander core logic: hardware independent, unit tested on the host.
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// ---------------------------------------------------------------- packet --

#define FFX_MAGIC 0xFB
#define FFX_VERSION 1
#define FFX_PACKET_LEN 7

// TX is about to deep-sleep: RX should release everything right away.
#define FFX_FLAG_SLEEP 0x01

typedef struct {
    uint16_t seq;
    uint16_t buttons; // bit n set = button n pressed
    uint8_t flags;
} ffx_packet_t;

// Returns bytes written (FFX_PACKET_LEN) or 0 if buf is too small.
size_t ffx_packet_encode(const ffx_packet_t *pkt, uint8_t *buf, size_t len);
// Returns false for anything that is not a valid packet of our version.
bool ffx_packet_decode(const uint8_t *buf, size_t len, ffx_packet_t *pkt);

// ------------------------------------------------------------- debouncer --
// Eager debounce: a change is reported on its first edge, then that button
// ignores further changes for lock_ms. Zero added latency, bounce-proof.

typedef struct {
    uint16_t state;
    uint16_t locked;
    uint32_t lock_ms;
    uint32_t lock_until[16];
} ffx_debounce_t;

void ffx_debounce_init(ffx_debounce_t *d, uint16_t initial, uint32_t lock_ms);
// Feed raw button mask; returns the debounced mask.
uint16_t ffx_debounce_update(ffx_debounce_t *d, uint16_t raw, uint32_t now_ms);

// ---------------------------------------------------------- link monitor --

typedef struct {
    bool up;
    uint32_t timeout_ms;
    uint32_t last_rx_ms;
    uint16_t last_seq;
    uint32_t received; // accepted packets
    uint32_t lost;     // sequence gaps while the link was up
    uint32_t stale;    // duplicates / out of order, dropped
} ffx_link_t;

void ffx_link_init(ffx_link_t *l, uint32_t timeout_ms);
// Returns true if the packet is new and should be applied.
bool ffx_link_on_packet(ffx_link_t *l, uint16_t seq, uint32_t now_ms);
// Force the link down (e.g. TX announced sleep).
void ffx_link_drop(ffx_link_t *l);
// Times out the link; returns current up state.
bool ffx_link_poll(ffx_link_t *l, uint32_t now_ms);

// ----------------------------------------------------------- pin mapping --

// GPIO level bitmap (bit = GPIO number) -> button mask.
uint16_t ffx_levels_to_buttons(uint32_t levels, const uint8_t *pins, size_t n, bool active_low);

// Button mask -> GPIO bits to set high / clear low.
void ffx_buttons_to_levels(uint16_t buttons, const uint8_t *pins, size_t n, bool active_low, uint32_t *set_mask,
                           uint32_t *clear_mask);

#ifdef __cplusplus
}
#endif
