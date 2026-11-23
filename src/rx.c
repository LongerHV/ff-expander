// Base side: receive state over ESP-NOW, drive the 74HC165 parallel inputs.
#if FFX_ROLE_RX

#include <stdio.h>
#include <string.h>

#include "driver/gpio.h"
#include "ffx_config.h"
#include "ffx_core.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "platform.h"
#include "soc/gpio_reg.h"

static const uint8_t PINS[FFX_NUM_BUTTONS] = FFX_RX_PINS;
static const uint8_t TX_MAC[6] = FFX_TX_MAC;

static uint32_t s_out_pins_mask;
static uint32_t s_led_mask = 1u << FFX_PIN_LED;

// Link state and outputs are touched from the Wi-Fi task (receive callback)
// and the watchdog task; this lock keeps them consistent.
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static ffx_link_t s_link;
static uint16_t s_buttons;

typedef struct {
    uint32_t t_ms;
    uint16_t buttons;
    uint16_t seq;
    bool link_up;
} rx_event_t;
static QueueHandle_t s_log_q;

// Write all outputs (and the LED) in one register write, so the XDRIVE never
// latches a half-updated button set. Caller holds s_lock.
static void write_outputs_locked(uint16_t buttons, bool link_up) {
    uint32_t set, clr;
    ffx_buttons_to_levels(buttons, PINS, FFX_NUM_BUTTONS, FFX_RX_PRESSED_LOW, &set, &clr);
    uint32_t out = REG_READ(GPIO_OUT_REG);
    out = (out & ~(s_out_pins_mask | s_led_mask)) | set | (link_up ? 0 : s_led_mask); // LED active low
    REG_WRITE(GPIO_OUT_REG, out);
}

static void apply_locked(uint16_t buttons, uint16_t seq, bool link_up, bool force) {
    bool changed = buttons != s_buttons;
    if (!changed && !force) return;
    s_buttons = buttons;
    write_outputs_locked(buttons, link_up);
    rx_event_t ev = {now_ms(), buttons, seq, link_up};
    xQueueSendFromISR(s_log_q, &ev, NULL); // safe inside a critical section
}

static void on_recv(const uint8_t *data, int len) {
    ffx_packet_t pkt;
    if (!ffx_packet_decode(data, (size_t)len, &pkt)) return;
    uint32_t now = now_ms();

    taskENTER_CRITICAL(&s_lock);
    bool was_up = s_link.up;
    if (ffx_link_on_packet(&s_link, pkt.seq, now)) {
        if (pkt.flags & FFX_FLAG_SLEEP) {
            ffx_link_drop(&s_link);
            apply_locked(0, pkt.seq, false, true);
        } else {
            apply_locked(pkt.buttons, pkt.seq, true, !was_up);
        }
    }
    taskEXIT_CRITICAL(&s_lock);
}

static void watchdog_task(void *arg) {
    (void)arg;
    TickType_t wake = xTaskGetTickCount();
    for (;;) {
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(5));
        taskENTER_CRITICAL(&s_lock);
        bool was_up = s_link.up;
        if (was_up && !ffx_link_poll(&s_link, now_ms())) apply_locked(0, s_link.last_seq, false, true);
        taskEXIT_CRITICAL(&s_lock);
    }
}

static void log_task(void *arg) {
    (void)arg;
    rx_event_t ev;
    for (;;) {
        if (xQueueReceive(s_log_q, &ev, portMAX_DELAY))
            printf("RX t=%lu btn=0x%03x seq=%u link=%s\n", (unsigned long)ev.t_ms, ev.buttons, ev.seq,
                   ev.link_up ? "up" : "down");
    }
}

static void on_command(char *line) {
    if (!strcmp(line, "s")) {
        taskENTER_CRITICAL(&s_lock);
        ffx_link_t l = s_link;
        uint16_t b = s_buttons;
        taskEXIT_CRITICAL(&s_lock);
        printf("STAT link=%s btn=0x%03x received=%lu lost=%lu stale=%lu\n", l.up ? "up" : "down", b,
               (unsigned long)l.received, (unsigned long)l.lost, (unsigned long)l.stale);
    } else {
        printf("ERR commands: s\n");
    }
}

void role_main(void) {
    for (int i = 0; i < FFX_NUM_BUTTONS; i++) s_out_pins_mask |= 1u << PINS[i];

    ffx_link_init(&s_link, FFX_LINK_TIMEOUT_MS);
    // Released state before the pins become outputs: no glitch at boot.
    write_outputs_locked(0, false);
    gpio_config_t out = {.pin_bit_mask = s_out_pins_mask, .mode = GPIO_MODE_OUTPUT};
    ESP_ERROR_CHECK(gpio_config(&out));

    s_log_q = xQueueCreate(64, sizeof(rx_event_t));
    console_start(on_command);
    printf("INFO role=rx\n");
    xTaskCreate(log_task, "log", 3072, NULL, 1, NULL);
    xTaskCreate(watchdog_task, "watchdog", 3072, NULL, 10, NULL);
    radio_init(TX_MAC, on_recv, NULL);
}

#endif
