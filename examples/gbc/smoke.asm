SECTION "Entry", ROM0[$100]
    nop
    jp Start
    ds $150 - @, 0
SECTION "Program", ROM0[$150]
Start:
    di
    ld sp, $fffe
    ld a, $0a
    ld [$0000], a
    ld a, $91
    ldh [$ff40], a
.loop:
    jr .loop
