#include <radium.h>

#include "console.h"
#include "syscall.h"
#include "util.h"

static uint32_t
syscall_regdump(registers_t* regs)
{
    printf("syscall_regdump: eax=%x, ebx=%x, ecx=%x, edx=%x\n", regs->eax, regs->ebx, regs->ecx, regs->edx);
    printf("                 esp=%x, ebp=%x, esi=%x, edi=%x\n", regs->esp, regs->ebp, regs->esi, regs->edi);

    return 0;
}

typedef uint32_t(syscall_t)(registers_t*);

static syscall_t*
syscall_table[] = {
    [SYS_REGDUMP] = syscall_regdump,
};

void
syscall_dispatch(registers_t* regs)
{
    if(regs->eax > countof(syscall_table)) {
        regs->eax = -ENOSYS;
        return;
    }

    syscall_t* func = syscall_table[regs->eax];

    if(!func) {
        regs->eax = -ENOSYS;
        return;
    }

    regs->eax = func(regs);
}
