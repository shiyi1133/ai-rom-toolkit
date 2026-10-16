.syntax unified
.cpu arm7tdmi
.section .text
.arm
.global _start
_start:
    b start
    .space 0xBC
start:
    ldr r0, =0x04000000
    ldr r1, =0x0403
    strh r1, [r0]
    ldr r0, =0x06000000
    mov r1, #31
    strh r1, [r0]
loop:
    b loop
    .ltorg
.thumb
.thumb_func
thumb_smoke:
    movs r0, #1
    bx lr
