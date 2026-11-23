#include "ffx_core.h"

// ---------------------------------------------------------------- packet --

size_t ffx_packet_encode(const ffx_packet_t *pkt, uint8_t *buf, size_t len) {
    if (len < FFX_PACKET_LEN) return 0;
    buf[0] = FFX_MAGIC;
    buf[1] = FFX_VERSION;
    buf[2] = (uint8_t)(pkt->seq & 0xFF);
    buf[3] = (uint8_t)(pkt->seq >> 8);
    buf[4] = (uint8_t)(pkt->buttons & 0xFF);
    buf[5] = (uint8_t)(pkt->buttons >> 8);
    buf[6] = pkt->flags;
    return FFX_PACKET_LEN;
}

bool ffx_packet_decode(const uint8_t *buf, size_t len, ffx_packet_t *pkt) {
    if (len != FFX_PACKET_LEN || buf[0] != FFX_MAGIC || buf[1] != FFX_VERSION) return false;
    pkt->seq = (uint16_t)(buf[2] | (buf[3] << 8));
    pkt->buttons = (uint16_t)(buf[4] | (buf[5] << 8));
    pkt->flags = buf[6];
    return true;
}

// ------------------------------------------------------------- debouncer --

static bool time_before(uint32_t a, uint32_t b) { return (int32_t)(a - b) < 0; }

void ffx_debounce_init(ffx_debounce_t *d, uint16_t initial, uint32_t lock_ms) {
    d->state = initial;
    d->locked = 0;
    d->lock_ms = lock_ms;
    for (int i = 0; i < 16; i++) d->lock_until[i] = 0;
}

uint16_t ffx_debounce_update(ffx_debounce_t *d, uint16_t raw, uint32_t now_ms) {
    for (int i = 0; i < 16; i++) {
        uint16_t bit = (uint16_t)(1u << i);
        if ((d->locked & bit) && !time_before(now_ms, d->lock_until[i])) d->locked &= (uint16_t)~bit;
        if (((raw ^ d->state) & bit) && !(d->locked & bit)) {
            d->state ^= bit;
            d->locked |= bit;
            d->lock_until[i] = now_ms + d->lock_ms;
        }
    }
    return d->state;
}

// ---------------------------------------------------------- link monitor --

void ffx_link_init(ffx_link_t *l, uint32_t timeout_ms) {
    *l = (ffx_link_t){.timeout_ms = timeout_ms};
}

bool ffx_link_on_packet(ffx_link_t *l, uint16_t seq, uint32_t now_ms) {
    if (l->up) {
        int16_t delta = (int16_t)(uint16_t)(seq - l->last_seq);
        if (delta <= 0) {
            l->stale++;
            return false;
        }
        l->lost += (uint32_t)(delta - 1);
    }
    l->up = true;
    l->last_seq = seq;
    l->last_rx_ms = now_ms;
    l->received++;
    return true;
}

void ffx_link_drop(ffx_link_t *l) { l->up = false; }

bool ffx_link_poll(ffx_link_t *l, uint32_t now_ms) {
    if (l->up && !time_before(now_ms, l->last_rx_ms + l->timeout_ms)) l->up = false;
    return l->up;
}

// ----------------------------------------------------------- pin mapping --

uint16_t ffx_levels_to_buttons(uint32_t levels, const uint8_t *pins, size_t n, bool active_low) {
    if (active_low) levels = ~levels;
    uint16_t buttons = 0;
    for (size_t i = 0; i < n && i < 16; i++)
        if (levels & (1u << pins[i])) buttons |= (uint16_t)(1u << i);
    return buttons;
}

void ffx_buttons_to_levels(uint16_t buttons, const uint8_t *pins, size_t n, bool active_low,
                           uint32_t *set_mask, uint32_t *clear_mask) {
    uint32_t high = 0, low = 0;
    for (size_t i = 0; i < n && i < 16; i++) {
        bool pressed = buttons & (1u << i);
        if (pressed != active_low) high |= 1u << pins[i];
        else low |= 1u << pins[i];
    }
    *set_mask = high;
    *clear_mask = low;
}
