#!/usr/bin/env ash

if test -f "$CRONFILE"; then
  echo "FILE HERE"
else
  ls /config
  echo "*/5 * * * * /usr/local/bin/dionysia-tools --config \$CONFIGFILE plex-recently-added
# Default Settings" > $CRONFILE
fi;

crontab $CRONFILE
crond -f -L /dev/stdout
