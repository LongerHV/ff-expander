// Shared ESP32 plumbing for both roles: board, radio, console.
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "esp_now.h"

// Board: RF switch / antenna, user LED.
void board_init(void);
void board_led(bool on);
uint32_t now_ms(void);

// Radio: Wi-Fi STA + ESP-NOW with a single fixed peer.
// recv_cb only gets packets from the peer.
typedef void (*radio_recv_cb_t)(const uint8_t *data, int len);
typedef void (*radio_sent_cb_t)(bool ok);
void radio_init(const uint8_t peer_mac[6], radio_recv_cb_t on_recv, radio_sent_cb_t on_sent);
bool radio_send(const uint8_t *data, size_t len);

// Console: line-oriented commands over USB Serial/JTAG.
typedef void (*console_handler_t)(char *line);
void console_start(console_handler_t handler);
