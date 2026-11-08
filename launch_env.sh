#!/usr/bin/env bash

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1

# models get lower priority than ui
# - ui is ~5ms
# - modeld is 20ms
# - DM is 10ms
# in order to run ui at 60fps (16.67ms), we need to allow
# it to preempt the model workloads. we have enough
# headroom for this until ui is moved to the CPU.
export QCOM_PRIORITY=12

# lean build: no driver monitoring, cabin camera unused
export DISABLE_DRIVER=1

export AGNOS_VERSION="20.2-c3xl"
export AGNOS_ACCEPTED_VERSIONS="$AGNOS_VERSION"

# Keep userspace Bluetooth disabled during the AGNOS 20.2-c3xl migration.
export DISABLE_BLUETOOTH=1

export STAGING_ROOT="/data/safe_staging"

# Force Simplified Chinese UI on every boot.
mkdir -p /data/params/d
printf '%s' "zh-CHS" > /data/params/d/LanguageSetting
printf '%s' "0" > /data/params/d/BluetoothEnabled
printf '%s' "0" > /data/params/d/BluetoothAudioTestActive

# C3XL exposes the system D-Bus socket at /run/dbus.
if [ -S /run/dbus/system_bus_socket ]; then
  export DBUS_SYSTEM_BUS_ADDRESS="unix:path=/run/dbus/system_bus_socket"
fi

# C3XL has no battery-backed RTC. Seed a recent time so TLS/model downloads work
# before NTP or GPS corrects the clock.
if [ "$(date +%Y%m%d)" -lt 20261009 ]; then
  sudo date -s "2026-10-09 12:00:00" >/dev/null 2>&1
  printf 'seeded %s (was earlier than 2026-10-09)\n' "$(date -Is)" >> /data/time_seed.log 2>/dev/null
fi
