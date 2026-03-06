#!/bin/bash
set -e

mount --bind /etc/ipsec-ns/hostA /etc
mkdir -p /etc/ipsec.d/run
chmod 777 /etc/ipsec.d/run
ls -ltr /etc/ipsec.d/run/

#/usr/sbin/charon-systemd --use-syslog &
setsid /usr/sbin/charon-systemd --use-syslogd >/var/log/charon-wrapper.log 2>&1 &
CHARON_PID=$!
echo "charon started with PID $CHARON_PID"

# Verify process is running
if ! kill -0 $CHARON_PID 2>/dev/null; then
    echo "charon failed to start"
    exit 1
fi

echo "charon started with PID $CHARON_PID"
exit 0
