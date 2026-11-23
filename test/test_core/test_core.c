#include <unity.h>

#include "ffx_core.h"

void setUp(void) {}
void tearDown(void) {}

// ---------------------------------------------------------------- packet --

static void test_packet_roundtrip(void) {
    ffx_packet_t in = {.seq = 0xBEEF, .buttons = 0x03A5, .flags = FFX_FLAG_SLEEP}, out = {0};
    uint8_t buf[FFX_PACKET_LEN];
    TEST_ASSERT_EQUAL(FFX_PACKET_LEN, ffx_packet_encode(&in, buf, sizeof buf));
    TEST_ASSERT_TRUE(ffx_packet_decode(buf, sizeof buf, &out));
    TEST_ASSERT_EQUAL_HEX16(in.seq, out.seq);
    TEST_ASSERT_EQUAL_HEX16(in.buttons, out.buttons);
    TEST_ASSERT_EQUAL_HEX8(in.flags, out.flags);
}

static void test_packet_encode_small_buffer(void) {
    ffx_packet_t in = {0};
    uint8_t buf[FFX_PACKET_LEN - 1];
    TEST_ASSERT_EQUAL(0, ffx_packet_encode(&in, buf, sizeof buf));
}

static void test_packet_rejects_garbage(void) {
    ffx_packet_t in = {.seq = 1, .buttons = 2}, out;
    uint8_t buf[FFX_PACKET_LEN];
    ffx_packet_encode(&in, buf, sizeof buf);

    TEST_ASSERT_FALSE(ffx_packet_decode(buf, sizeof buf - 1, &out)); // short
    buf[0] ^= 0xFF;
    TEST_ASSERT_FALSE(ffx_packet_decode(buf, sizeof buf, &out)); // magic
    buf[0] ^= 0xFF;
    buf[1] = FFX_VERSION + 1;
    TEST_ASSERT_FALSE(ffx_packet_decode(buf, sizeof buf, &out)); // version
}

// ------------------------------------------------------------- debouncer --

static void test_debounce_reports_first_edge_immediately(void) {
    ffx_debounce_t d;
    ffx_debounce_init(&d, 0, 5);
    TEST_ASSERT_EQUAL_HEX16(0x0001, ffx_debounce_update(&d, 0x0001, 100));
}

static void test_debounce_ignores_bounce_within_lock(void) {
    ffx_debounce_t d;
    ffx_debounce_init(&d, 0, 5);
    ffx_debounce_update(&d, 0x0001, 100);
    TEST_ASSERT_EQUAL_HEX16(0x0001, ffx_debounce_update(&d, 0x0000, 101));
    TEST_ASSERT_EQUAL_HEX16(0x0001, ffx_debounce_update(&d, 0x0001, 102));
    TEST_ASSERT_EQUAL_HEX16(0x0001, ffx_debounce_update(&d, 0x0000, 104));
    // lock expired: release goes through
    TEST_ASSERT_EQUAL_HEX16(0x0000, ffx_debounce_update(&d, 0x0000, 105));
}

static void test_debounce_buttons_independent(void) {
    ffx_debounce_t d;
    ffx_debounce_init(&d, 0, 5);
    ffx_debounce_update(&d, 0x0001, 100);
    // button 1 not locked by button 0's edge
    TEST_ASSERT_EQUAL_HEX16(0x0003, ffx_debounce_update(&d, 0x0003, 101));
}

static void test_debounce_time_wraparound(void) {
    ffx_debounce_t d;
    ffx_debounce_init(&d, 0, 5);
    ffx_debounce_update(&d, 0x0001, 0xFFFFFFFE);
    TEST_ASSERT_EQUAL_HEX16(0x0001, ffx_debounce_update(&d, 0x0000, 1));
    TEST_ASSERT_EQUAL_HEX16(0x0000, ffx_debounce_update(&d, 0x0000, 3));
}

static void test_debounce_initial_state(void) {
    ffx_debounce_t d;
    ffx_debounce_init(&d, 0x0200, 5);
    TEST_ASSERT_EQUAL_HEX16(0x0200, ffx_debounce_update(&d, 0x0200, 0));
}

// ---------------------------------------------------------- link monitor --

static void test_link_starts_down_and_comes_up(void) {
    ffx_link_t l;
    ffx_link_init(&l, 100);
    TEST_ASSERT_FALSE(ffx_link_poll(&l, 0));
    TEST_ASSERT_TRUE(ffx_link_on_packet(&l, 42, 10));
    TEST_ASSERT_TRUE(ffx_link_poll(&l, 10));
}

static void test_link_times_out(void) {
    ffx_link_t l;
    ffx_link_init(&l, 100);
    ffx_link_on_packet(&l, 1, 1000);
    TEST_ASSERT_TRUE(ffx_link_poll(&l, 1099));
    TEST_ASSERT_FALSE(ffx_link_poll(&l, 1100));
}

static void test_link_drops_duplicates_and_stale(void) {
    ffx_link_t l;
    ffx_link_init(&l, 100);
    ffx_link_on_packet(&l, 10, 0);
    TEST_ASSERT_FALSE(ffx_link_on_packet(&l, 10, 1));
    TEST_ASSERT_FALSE(ffx_link_on_packet(&l, 9, 2));
    TEST_ASSERT_EQUAL(2, l.stale);
    TEST_ASSERT_TRUE(ffx_link_on_packet(&l, 11, 3));
}

static void test_link_counts_gaps_and_seq_wrap(void) {
    ffx_link_t l;
    ffx_link_init(&l, 100);
    ffx_link_on_packet(&l, 0xFFFE, 0);
    TEST_ASSERT_TRUE(ffx_link_on_packet(&l, 0x0001, 1)); // skipped FFFF, 0000
    TEST_ASSERT_EQUAL(2, l.lost);
    TEST_ASSERT_EQUAL(2, l.received);
}

static void test_link_accepts_any_seq_after_timeout(void) {
    // TX rebooted: sequence restarts low, must be accepted once link is down
    ffx_link_t l;
    ffx_link_init(&l, 100);
    ffx_link_on_packet(&l, 5000, 0);
    ffx_link_poll(&l, 500);
    TEST_ASSERT_TRUE(ffx_link_on_packet(&l, 0, 501));
    TEST_ASSERT_EQUAL(0, l.lost);
}

static void test_link_drop(void) {
    ffx_link_t l;
    ffx_link_init(&l, 100);
    ffx_link_on_packet(&l, 1, 0);
    ffx_link_drop(&l);
    TEST_ASSERT_FALSE(ffx_link_poll(&l, 1));
}

// ----------------------------------------------------------- pin mapping --

static const uint8_t PINS[] = {1, 2, 21, 22, 23, 16, 17, 19, 20, 18};
#define NPINS (sizeof PINS / sizeof PINS[0])

static void test_levels_to_buttons_active_low(void) {
    uint32_t levels = 0xFFFFFFFF & ~(1u << 1) & ~(1u << 18); // GPIO1, GPIO18 pulled low
    TEST_ASSERT_EQUAL_HEX16((1u << 0) | (1u << 9), ffx_levels_to_buttons(levels, PINS, NPINS, true));
}

static void test_levels_to_buttons_active_high(void) {
    TEST_ASSERT_EQUAL_HEX16(1u << 2, ffx_levels_to_buttons(1u << 21, PINS, NPINS, false));
}

static void test_buttons_to_levels_active_low(void) {
    uint32_t set, clr;
    ffx_buttons_to_levels(0x0001, PINS, NPINS, true, &set, &clr);
    TEST_ASSERT_EQUAL_HEX32(1u << 1, clr);
    uint32_t all = 0;
    for (size_t i = 0; i < NPINS; i++) all |= 1u << PINS[i];
    TEST_ASSERT_EQUAL_HEX32(all & ~(1u << 1), set);
}

static void test_buttons_to_levels_active_high(void) {
    uint32_t set, clr;
    ffx_buttons_to_levels(0x0200, PINS, NPINS, false, &set, &clr);
    TEST_ASSERT_EQUAL_HEX32(1u << 18, set);
    TEST_ASSERT_EQUAL_HEX32(0, set & clr);
}

int main(void) {
    UNITY_BEGIN();
    RUN_TEST(test_packet_roundtrip);
    RUN_TEST(test_packet_encode_small_buffer);
    RUN_TEST(test_packet_rejects_garbage);
    RUN_TEST(test_debounce_reports_first_edge_immediately);
    RUN_TEST(test_debounce_ignores_bounce_within_lock);
    RUN_TEST(test_debounce_buttons_independent);
    RUN_TEST(test_debounce_time_wraparound);
    RUN_TEST(test_debounce_initial_state);
    RUN_TEST(test_link_starts_down_and_comes_up);
    RUN_TEST(test_link_times_out);
    RUN_TEST(test_link_drops_duplicates_and_stale);
    RUN_TEST(test_link_counts_gaps_and_seq_wrap);
    RUN_TEST(test_link_accepts_any_seq_after_timeout);
    RUN_TEST(test_link_drop);
    RUN_TEST(test_levels_to_buttons_active_low);
    RUN_TEST(test_levels_to_buttons_active_high);
    RUN_TEST(test_buttons_to_levels_active_low);
    RUN_TEST(test_buttons_to_levels_active_high);
    return UNITY_END();
}
