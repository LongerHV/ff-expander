#include "platform.h"

#include <stdio.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"
#include "esp_check.h"
#include "esp_event.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "ffx_config.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"

// ----------------------------------------------------------------- board --

void board_init(void) {
    gpio_config_t out = {
        .pin_bit_mask = (1ULL << FFX_PIN_RF_SWITCH_EN) | (1ULL << FFX_PIN_ANT_SELECT) | (1ULL << FFX_PIN_LED),
        .mode = GPIO_MODE_OUTPUT,
    };
    ESP_ERROR_CHECK(gpio_config(&out));
    gpio_set_level(FFX_PIN_RF_SWITCH_EN, 0);
    gpio_set_level(FFX_PIN_ANT_SELECT, 0);
    board_led(false);
}

void board_led(bool on) { gpio_set_level(FFX_PIN_LED, on ? 0 : 1); }

uint32_t now_ms(void) { return (uint32_t)(esp_timer_get_time() / 1000); }

// ----------------------------------------------------------------- radio --

static uint8_t s_peer[6];
static radio_recv_cb_t s_on_recv;
static radio_sent_cb_t s_on_sent;

static void espnow_recv(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
    if (memcmp(info->src_addr, s_peer, 6) != 0) return;
    if (s_on_recv) s_on_recv(data, len);
}

static void espnow_sent(const esp_now_send_info_t *info, esp_now_send_status_t status) {
    (void)info;
    if (s_on_sent) s_on_sent(status == ESP_NOW_SEND_SUCCESS);
}

void radio_init(const uint8_t peer_mac[6], radio_recv_cb_t on_recv, radio_sent_cb_t on_sent) {
    memcpy(s_peer, peer_mac, 6);
    s_on_recv = on_recv;
    s_on_sent = on_sent;

    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());
    // Modem sleep would add 10-100 ms of latency; keep the radio awake.
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    ESP_ERROR_CHECK(esp_wifi_set_channel(FFX_WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE));

    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_register_recv_cb(espnow_recv));
    ESP_ERROR_CHECK(esp_now_register_send_cb(espnow_sent));

    esp_now_peer_info_t peer = {
        .channel = FFX_WIFI_CHANNEL,
        .ifidx = WIFI_IF_STA,
        .encrypt = false,
    };
    memcpy(peer.peer_addr, s_peer, 6);
    ESP_ERROR_CHECK(esp_now_add_peer(&peer));

    esp_now_rate_config_t rate = {.phymode = FFX_PHY_MODE, .rate = FFX_PHY_RATE};
    ESP_ERROR_CHECK(esp_now_set_peer_rate_config(s_peer, &rate));

    uint8_t mac[6];
    ESP_ERROR_CHECK(esp_wifi_get_mac(WIFI_IF_STA, mac));
    printf("INFO mac=" MACSTR " peer=" MACSTR " ch=%d\n", MAC2STR(mac), MAC2STR(s_peer), FFX_WIFI_CHANNEL);
}

bool radio_send(const uint8_t *data, size_t len) { return esp_now_send(s_peer, data, len) == ESP_OK; }

// --------------------------------------------------------------- console --

static void console_task(void *arg) {
    console_handler_t handler = (console_handler_t)arg;
    char line[64];
    size_t n = 0;
    for (;;) {
        uint8_t c;
        if (usb_serial_jtag_read_bytes(&c, 1, portMAX_DELAY) != 1) continue;
        if (c == '\r' || c == '\n') {
            if (n == 0) continue;
            line[n] = '\0';
            n = 0;
            handler(line);
        } else if (n < sizeof line - 1) {
            line[n++] = (char)c;
        }
    }
}

void console_start(console_handler_t handler) {
    usb_serial_jtag_driver_config_t cfg = USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&cfg));
    usb_serial_jtag_vfs_use_driver();
    setvbuf(stdout, NULL, _IOLBF, 0);
    xTaskCreate(console_task, "console", 3072, (void *)handler, 2, NULL);
}
