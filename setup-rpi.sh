#!/usr/bin/env bash
set -Eeuo pipefail

# Everything is stored in the current working directory.
CWD="$(pwd -P)"
WORK="$CWD"
IMAGE="${1:-}"

if [[ -z "$IMAGE" ]]; then
    echo "Usage: $0 ./raspios.img"
    exit 1
fi

IMAGE="$(realpath "$IMAGE")"

if [[ ! -f "$IMAGE" ]]; then
    echo "ERROR: Image not found: $IMAGE"
    exit 1
fi

for cmd in qemu-img qemu-system-aarch64 fdtoverlay losetup blkid mount umount sed; do
    command -v "$cmd" >/dev/null || {
        echo "Missing command: $cmd"
        echo "Install it with: sudo apt install qemu-system-arm qemu-utils device-tree-compiler"
        exit 1
    }
done

# All files are stored directly in CWD.
KERNEL="$WORK/kernel8.img"
DTB="$WORK/bcm2710-rpi-3-b-nobt.dtb"

# Temporary mount points are also stored in CWD.
BOOT="$WORK/.rpi-boot-mnt"
ROOT="$WORK/.rpi-root-mnt"
mkdir -p "$BOOT" "$ROOT"

LOOP=""
BOOT_MOUNTED=0
ROOT_MOUNTED=0

cleanup() {
    if [[ "$ROOT_MOUNTED" == 1 ]]; then
        sudo umount "$ROOT" || true
    fi
    if [[ "$BOOT_MOUNTED" == 1 ]]; then
        sudo umount "$BOOT" || true
    fi
    if [[ -n "$LOOP" ]]; then
        sudo losetup -d "$LOOP" || true
    fi
    rmdir "$BOOT" "$ROOT" 2>/dev/null || true
}
trap cleanup EXIT

echo "== Checking and resizing the image =="
qemu-img resize "$IMAGE" 4G

echo "== Attaching image partitions =="
LOOP="$(sudo losetup --find --show --partscan "$IMAGE")"
echo "Loop device: $LOOP"

BOOT_PART="${LOOP}p1"
ROOT_PART="${LOOP}p2"

if [[ ! -b "$BOOT_PART" || ! -b "$ROOT_PART" ]]; then
    echo "ERROR: Partitions p1/p2 not found. Check that the image contains boot and root partitions."
    exit 1
fi

ROOT_PARTUUID="$(sudo blkid -s PARTUUID -o value "$ROOT_PART")"
echo "Root PARTUUID: $ROOT_PARTUUID"

sudo mount "$BOOT_PART" "$BOOT"
BOOT_MOUNTED=1
sudo mount "$ROOT_PART" "$ROOT"
ROOT_MOUNTED=1

for f in kernel8.img bcm2710-rpi-3-b.dtb overlays/disable-bt.dtbo; do
    if [[ ! -f "$BOOT/$f" ]]; then
        echo "ERROR: Missing $f in the boot partition"
        exit 1
    fi
done

echo "== Copying the kernel to the current directory =="
sudo cp "$BOOT/kernel8.img" "$KERNEL"
sudo chown "$(id -u):$(id -g)" "$KERNEL"

echo "== Creating a DTB with the Bluetooth UART disabled =="
fdtoverlay \
    -i "$BOOT/bcm2710-rpi-3-b.dtb" \
    -o "$DTB" \
    "$BOOT/overlays/disable-bt.dtbo"

echo "== Setting the pi user's password =="
SHADOW="$ROOT/etc/shadow"
PASSWORD_HASH='$6$1rV.H9wJ83d1igQ7$590dztXGFTXsgGeuQmkG4hnX1yA..LvlrK72yV.3dbfEO2IG8W8gnVNSk3eSIs99LOwY5gT6IozcLdnHTtZeY0'

if ! sudo grep -q '^pi:' "$SHADOW"; then
    echo "ERROR: User pi not found in /etc/shadow"
    exit 1
fi

sudo sed -i "/^pi:/s|^[^:]*:[^:]*:|pi:${PASSWORD_HASH}:|" "$SHADOW"
echo "Password for pi updated"

echo "== Enabling UART login =="
sudo mkdir -p "$ROOT/etc/systemd/system/getty.target.wants"
sudo ln -sfn /lib/systemd/system/serial-getty@.service \
    "$ROOT/etc/systemd/system/getty.target.wants/serial-getty@ttyAMA0.service"
sudo rm -f \
    "$ROOT/etc/systemd/system/getty.target.wants/serial-getty@ttyAMA1.service"

sync

echo
echo "== Preparation complete =="
echo "Working directory: $WORK"
echo "Image: $IMAGE"
echo "Kernel: $KERNEL"
echo "DTB: $DTB"
echo "Root PARTUUID: $ROOT_PARTUUID"
echo
echo "After unmounting the partitions, run:"
echo "  ./run-rpi.sh \"$IMAGE\" \"$ROOT_PARTUUID\""