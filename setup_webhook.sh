#!/bin/bash
set -eu

echo "CryptoPredict recovery: legacy webhook auto-deploy is DISABLED."
echo "This script intentionally performs no git pull, package install, service restart, firewall, or nginx mutation."
echo
echo "Use docs/HTTPS_RECOVERY_STAGING.md for the reviewed manual staging procedure."
echo "The standalone webhook, if installed, authenticates requests but returns deployment_disabled and executes no commands."
exit 0
