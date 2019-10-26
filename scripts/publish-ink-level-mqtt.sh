#!/bin/bash

#to get it working
#1. install hplip
#2. run hp-setup
#credits for this script and more information: https://github.com/hokus15/home-assistant-conifig/blob/fd6880a8ec2d1d55bf77aa9f8f799ff23390aad6/README.md#monitor-printer-ink-levels

#read cfg format: variable="value"
source /usr/share/hassio/homeassistant/scripts/publish-ink-level-mqtt.cfg

hp_info=$(hp-info 2>&1)

#Publish status
status=$(echo "$hp_info" | grep  -oP "(?<=status-desc\s{18})(.*\S)")
mosquitto_pub -h $mqtt_hostname -p $mqtt_port -t "home/printer/status" -r -m "$status"

#Publish ink levels
ink_levels=$(echo "$hp_info" | grep -oP "(?<=agent[1-4]-level\s{18})(.*\S)" | tr "\n" ",")

colors=(
     'black'
     'cyan'
     'magenta'
     'yellow'
   )
if [ -n "${ink_levels}" ]; then
    IFS=',' read -r -a ink_levels_array <<< "$ink_levels"
    for index in "${!ink_levels_array[@]}"
    do
        if [ -n "${ink_levels_array[index]}" ]; then
           mosquitto_pub -h $mqtt_hostname -p $mqtt_port -t "home/printer/${colors[index]}" -r -m "${ink_levels_array[index]}"
        fi
    done
fi
