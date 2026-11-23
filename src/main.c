#include <stdio.h>

#include "esp_app_desc.h"
#include "platform.h"

#if !(FFX_ROLE_TX ^ FFX_ROLE_RX)
#error "Build with exactly one of -DFFX_ROLE_TX=1 or -DFFX_ROLE_RX=1 (use env tx or rx)"
#endif

void role_main(void);

void app_main(void) {
    printf("INFO ff-expander %s\n", esp_app_get_description()->version);
    board_init();
    role_main();
}
