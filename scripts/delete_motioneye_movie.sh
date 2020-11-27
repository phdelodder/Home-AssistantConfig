#!/bin/bash
timeout=5

username="admin"
password=""

motion_camera_id=$1
filename="$2.mp4"
event="$3"

echo "$(date -u)" "delete_motioneye_movie start up with paramaters: motion_camera_id -> ${motion_camera_id} || filename -> ${filename} || event -> ${event}" >> /config/scripts/delete_motioneye_movie.log

uri="/movie/$motion_camera_id/delete/$filename?_username=$username"
data="{}"
signature=$(echo -n "POST:$uri:$data:$password" | sha1sum | cut -d ' ' -f 1)
port="8765"

curl -s -S -m $timeout -H "Content-Type: application/json" -X POST "http://192.168.0.207:$port$uri&_signature=$signature" -d "$data" >> /config/scripts/delete_motioneye_movie.log

