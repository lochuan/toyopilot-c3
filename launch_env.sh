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

if [ -z "$AGNOS_VERSION" ]; then
  export AGNOS_VERSION="19.7-c3xl-dev-bt"
fi

if [ -z "$AGNOS_ACCEPTED_VERSIONS" ]; then
  export AGNOS_ACCEPTED_VERSIONS="19.7-c3xl-dev-bt"
fi

export STAGING_ROOT="/data/safe_staging"

# Force Simplified Chinese UI on every boot.
mkdir -p /data/params/d
printf '%s' "zh-CHS" > /data/params/d/LanguageSetting

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
