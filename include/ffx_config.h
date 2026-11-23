// ff-expander build-time configuration.
#pragma once

#include "esp_wifi_types.h"

// ---- Pairing: Wi-Fi STA MAC of each board (printed at boot) --------------
#define FFX_TX_MAC {0x10, 0xBD, 0xA3, 0xB1, 0xB9, 0x84}
#define FFX_RX_MAC {0x10, 0xBD, 0xA3, 0xB1, 0xB9, 0x00}

// ---- Radio ----------------------------------------------------------------
#define FFX_WIFI_CHANNEL 1
// 802.11g 12 Mbps: ~50 us airtime for our packet, robust at wheel-to-base range.
#define FFX_PHY_MODE WIFI_PHY_MODE_11G
#define FFX_PHY_RATE WIFI_PHY_RATE_12M

// ---- Timing ---------------------------------------------------------------
#define FFX_SCAN_PERIOD_MS 1     // TX button sampling
#define FFX_DEBOUNCE_LOCK_MS 5   // per-button lockout after an edge
#define FFX_HEARTBEAT_MS 20      // TX sends at least this often
#define FFX_LINK_TIMEOUT_MS 100  // RX releases all buttons after this silence
#ifndef FFX_IDLE_SLEEP_MS
#define FFX_IDLE_SLEEP_MS (10u * 60u * 1000u) // TX deep sleep after no activity; 0 = never
#endif

// ---- Pins (XIAO pad -> GPIO) ----------------------------------------------
// D0=0 D1=1 D2=2 D3=21 D4=22 D5=23 D6=16 D7=17 D8=19 D9=20 D10=18
#define FFX_NUM_BUTTONS 10

// TX: buttons 0..9 on D1..D10, wired to GND (internal pull-ups).
// D0 left free for a future battery-voltage divider (ADC).
#define FFX_TX_PINS {1, 2, 21, 22, 23, 16, 17, 19, 20, 18}
#define FFX_TX_ACTIVE_LOW 1
// Deep-sleep wake buttons: must be LP GPIOs (0..7) -> D1, D2.
#define FFX_TX_WAKE_PINS_MASK ((1ULL << 1) | (1ULL << 2))

// RX: outputs 0..9 on D0..D5, D10, D7..D9 -> 74HC165 parallel inputs.
// D6 (GPIO16, UART0 TX) is skipped: the boot ROM drives it at every reset.
#define FFX_RX_PINS {0, 1, 2, 21, 22, 23, 18, 17, 19, 20}
// 1: pressed = low, released = high (like a pull-up button box).
#define FFX_RX_PRESSED_LOW 1

// ---- On-board XIAO ESP32-C6 pins ------------------------------------------
#define FFX_PIN_RF_SWITCH_EN 3 // low = RF switch powered
#define FFX_PIN_ANT_SELECT 14  // low = on-board ceramic antenna
#define FFX_PIN_LED 15         // user LED, active low
