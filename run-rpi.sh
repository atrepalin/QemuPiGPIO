#!/usr/bin/env bash
set -Eeuo pipefail

CWD="$(pwd -P)"
IMAGE="${1:?Usage: ./run-rpi.sh ./raspios.img PARTUUID}"
ROOT_PARTUUID="${2:?Specify the root partition PARTUUID}"

IMAGE="$(realpath "$IMAGE")"

test -f "$IMAGE"
test -f "$CWD/kernel8.img"
test -f "$CWD/bcm2710-rpi-3-b-nobt.dtb"

rm -f "$CWD/qtest.sock"

exec qemu-system-aarch64 \
    -M raspi3b \
    -m 1G \
    -kernel "$CWD/kernel8.img" \
    -dtb "$CWD/bcm2710-rpi-3-b-nobt.dtb" \
    -drive "file=$IMAGE,if=sd,format=raw" \
    -append "console=ttyAMA0,115200 earlycon=pl011,mmio32,0x3f201000 root=PARTUUID=$ROOT_PARTUUID rootfstype=ext4 rw rootwait loglevel=7" \
    -display none \
    -serial mon:stdio \
    -monitor none \
    -no-reboot \
    -netdev user,id=net0 \
    -device usb-net,netdev=net0 \
    -qtest "unix:/tmp/qtest.sock,server=on,wait=off" \
    -qtest-log none