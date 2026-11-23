// Wheel side: scan buttons, debounce, send state over ESP-NOW.
#if FFX_ROLE_TX

#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/rtc_io.h"
#include "esp_random.h"
#include "esp_sleep.h"
#include "esp_system.h"
#include "ffx_config.h"
#include "ffx_core.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "platform.h"
#include "soc/gpio_reg.h"

static const uint8_t PINS[FFX_NUM_BUTTONS] = FFX_TX_PINS;
static const uint8_t RX_MAC[6] = FFX_RX_MAC;

// Simulated presses from the console, OR-ed with the real pins.
static _Atomic uint16_t s_sim_mask;
// Console "mute": stop transmitting until this time (link-loss test).
static _Atomic uint32_t s_mute_until;
static atomic_bool s_mute;
static atomic_bool s_force_sleep;
// Last send got no MAC-layer ACK: resend on the next tick.
static atomic_bool s_resend;
static _Atomic uint32_t s_sent_ok, s_sent_fail;

static QueueHandle_t s_log_q;
typedef struct {
    uint32_t t_ms;
    uint16_t buttons;
    uint16_t seq;
} tx_event_t;

static void on_sent(bool ok) {
    if (ok) {
        atomic_fetch_add(&s_sent_ok, 1);
    } else {
        atomic_fetch_add(&s_sent_fail, 1);
        atomic_store(&s_resend, true);
    }
}

static void send_state(uint16_t *seq, uint16_t buttons, uint8_t flags) {
    ffx_packet_t pkt = {.seq = ++*seq, .buttons = buttons, .flags = flags};
    uint8_t buf[FFX_PACKET_LEN];
    ffx_packet_encode(&pkt, buf, sizeof buf);
    if (!radio_send(buf, sizeof buf)) atomic_store(&s_resend, true);
}

static void enter_deep_sleep(uint16_t *seq) {
    printf("INFO sleeping\n");
    // Tell RX to release now rather than waiting for the link timeout.
    for (int i = 0; i < 3; i++) {
        send_state(seq, 0, FFX_FLAG_SLEEP);
        vTaskDelay(pdMS_TO_TICKS(5));
    }
    board_led(false);
    for (int i = 0; i < 64; i++) {
        if (!(FFX_TX_WAKE_PINS_MASK & (1ULL << i))) continue;
        rtc_gpio_pullup_en(i);
        rtc_gpio_pulldown_dis(i);
    }
    esp_sleep_enable_ext1_wakeup_io(FFX_TX_WAKE_PINS_MASK, ESP_EXT1_WAKEUP_ANY_LOW);
    esp_deep_sleep_start();
}

static void scan_task(void *arg) {
    (void)arg;
    ffx_debounce_t deb;
    uint16_t seq = (uint16_t)esp_random();
    uint16_t sent_buttons = 0;
    uint32_t last_send = 0, last_activity = now_ms();
    ffx_debounce_init(&deb, 0, FFX_DEBOUNCE_LOCK_MS);

    TickType_t wake = xTaskGetTickCount();
    for (;;) {
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(FFX_SCAN_PERIOD_MS));
        uint32_t now = now_ms();

        uint16_t raw = ffx_levels_to_buttons(REG_READ(GPIO_IN_REG), PINS, FFX_NUM_BUTTONS, FFX_TX_ACTIVE_LOW);
        uint16_t buttons = ffx_debounce_update(&deb, raw, now) | atomic_load(&s_sim_mask);
        bool changed = buttons != sent_buttons;

        if (changed) {
            last_activity = now;
            tx_event_t ev = {now, buttons, (uint16_t)(seq + 1)};
            xQueueSend(s_log_q, &ev, 0);
        }

        if (atomic_load(&s_mute) && (int32_t)(now - atomic_load(&s_mute_until)) >= 0) atomic_store(&s_mute, false);

        bool resend = atomic_exchange(&s_resend, false);
        if (!atomic_load(&s_mute) && (changed || resend || now - last_send >= FFX_HEARTBEAT_MS)) {
            send_state(&seq, buttons, 0);
            sent_buttons = buttons;
            last_send = now;
        }

        bool idle = FFX_IDLE_SLEEP_MS && buttons == 0 && now - last_activity >= FFX_IDLE_SLEEP_MS;
        if (idle || atomic_exchange(&s_force_sleep, false)) enter_deep_sleep(&seq);
    }
}

static void log_task(void *arg) {
    (void)arg;
    tx_event_t ev;
    for (;;) {
        if (xQueueReceive(s_log_q, &ev, portMAX_DELAY))
            printf("TX t=%lu btn=0x%03x seq=%u\n", (unsigned long)ev.t_ms, ev.buttons, ev.seq);
    }
}

static void on_command(char *line) {
    char *arg = strchr(line, ' ');
    if (arg) *arg++ = '\0';
    long v = arg ? strtol(arg, NULL, 0) : -1;

    if (!strcmp(line, "p") && v >= 0 && v < FFX_NUM_BUTTONS) {
        atomic_fetch_or(&s_sim_mask, (uint16_t)(1u << v));
    } else if (!strcmp(line, "r") && v >= 0 && v < FFX_NUM_BUTTONS) {
        atomic_fetch_and(&s_sim_mask, (uint16_t)~(1u << v));
    } else if (!strcmp(line, "m") && v >= 0) {
        atomic_store(&s_sim_mask, (uint16_t)(v & ((1u << FFX_NUM_BUTTONS) - 1)));
    } else if (!strcmp(line, "mute") && v > 0) {
        atomic_store(&s_mute_until, now_ms() + (uint32_t)v);
        atomic_store(&s_mute, true);
    } else if (!strcmp(line, "s")) {
        printf("STAT sim=0x%03x sent_ok=%lu sent_fail=%lu\n", atomic_load(&s_sim_mask),
               (unsigned long)atomic_load(&s_sent_ok), (unsigned long)atomic_load(&s_sent_fail));
        return;
    } else if (!strcmp(line, "sleep")) {
        atomic_store(&s_force_sleep, true);
    } else if (!strcmp(line, "reboot")) {
        esp_restart();
    } else {
        printf("ERR commands: p N | r N | m MASK | mute MS | s | sleep | reboot\n");
        return;
    }
    printf("OK\n");
}

void role_main(void) {
    gpio_config_t in = {.mode = GPIO_MODE_INPUT, .pull_up_en = FFX_TX_ACTIVE_LOW, .pull_down_en = !FFX_TX_ACTIVE_LOW};
    for (int i = 0; i < FFX_NUM_BUTTONS; i++) in.pin_bit_mask |= 1ULL << PINS[i];
    ESP_ERROR_CHECK(gpio_config(&in));
    // Wake pins were handed to the LP domain for deep sleep; take them back.
    for (int i = 0; i < 64; i++)
        if (FFX_TX_WAKE_PINS_MASK & (1ULL << i)) rtc_gpio_deinit(i);

    s_log_q = xQueueCreate(32, sizeof(tx_event_t));
    console_start(on_command);
    printf("INFO role=tx wake_causes=0x%lx\n", (unsigned long)esp_sleep_get_wakeup_causes());
    radio_init(RX_MAC, NULL, on_sent);
    xTaskCreate(log_task, "log", 3072, NULL, 1, NULL);
    xTaskCreate(scan_task, "scan", 4096, NULL, 10, NULL);
}

#endif
