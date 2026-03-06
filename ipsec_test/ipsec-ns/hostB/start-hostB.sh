#!/bin/bash
set -e

ls -tlr /etc/ipsec.d/run/
ps -ef | grep charon

