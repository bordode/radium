#include <console.h>
#include <panic.h>
#include <types.h>

#define RECORD_SIZE 32

typedef struct {
    uint32_t addr;
    char name[RECORD_SIZE - sizeof(uint32_t)];
}
symbol_record_t;

#define SYMBOL_ENTRIES (65536 / RECORD_SIZE)

extern symbol_record_t panic_symbols[SYMBOL_ENTRIES];

void
panic_print_backtrace_item(uint32_t addr)
{
    uint32_t base = 0;
    const char* name = "?";

    for(size_t i = 0; i < SYMBOL_ENTRIES; i++) {
        if(panic_symbols[i].addr == 0) {
            break;
        }
        if(panic_symbols[i].addr < addr && panic_symbols[i].addr > base) {
            base = panic_symbols[i].addr;
            name = panic_symbols[i].name;
        }
    }

    printf("  [<0x%x>] %s +%d\n", addr, name, addr - base);
}
