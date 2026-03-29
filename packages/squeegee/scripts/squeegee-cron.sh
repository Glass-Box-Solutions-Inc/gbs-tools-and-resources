#!/bin/bash
# Squeegee hourly cron wrapper
# Prevents system sleep during execution

cd /home/vncuser/gbs-tools-and-resources/packages/squeegee

# Use systemd-inhibit to prevent sleep during execution
/usr/bin/systemd-inhibit --what=sleep:idle --who="Squeegee" --why="Running documentation curation" \
  /usr/bin/node scripts/squeegee-manager.js full

