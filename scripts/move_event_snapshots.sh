#!/bin/bash

motion_camera="$1"
event="$2"

echo $(date -u) "move_event_snapshot start up with paramaters: motion_camera -> ${motion_camera} || event -> ${event} " >> /config/scripts/move_event_snapshot.log

/bin/mv -v /config/www/security/${motion_camera}_${event}_*.jpg /config/www/security/${motion_camera}_motion/ >> /config/scripts/move_event_snapshot.log