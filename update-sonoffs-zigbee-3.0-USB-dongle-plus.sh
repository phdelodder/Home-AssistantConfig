# $1: dev or master
# $2: router or coordinator
# $3: ttyUSB port number

# USE AT YOUR OWN RISK
# There is absolutely NO ERROR CHECKING.

# Must be run from a valid python environment.
# The HA Docker container has all requirements installed.

basepath=/config/sonoff_temp

cd /
rm -rf $basepath
mkdir $basepath
cd $basepath

# https://github.com/JelmerT/cc2538-bsl
wget https://github.com/JelmerT/cc2538-bsl/raw/master/cc2538-bsl.py

# https://github.com/Koenkk/Z-Stack-firmware
# No attempt is made to use github api to download latest versions.
# Urls will need to be edited to point to correct files as updates are posted to github.
mkdir master
cd master
# Master branch coordinator as of 5/11/22
wget https://github.com/Koenkk/Z-Stack-firmware/raw/master/coordinator/Z-Stack_3.x.0/bin/CC1352P2_CC2652P_launchpad_coordinator_20220219.zip
wget https://github.com/Koenkk/Z-Stack-firmware/raw/master/router/Z-Stack_3.x.0/bin/CC1352P2_CC2652P_launchpad_router_20220125.zip
for f in *.zip; do unzip $f; done 

cd ..
mkdir dev
cd dev
# Dev branch coordinator as of 5/11/22
wget https://github.com/Koenkk/Z-Stack-firmware/raw/develop/coordinator/Z-Stack_3.x.0/bin/CC1352P2_CC2652P_launchpad_coordinator_20220507.zip
wget https://github.com/Koenkk/Z-Stack-firmware/raw/develop/router/Z-Stack_3.x.0/bin/CC1352P2_CC2652P_launchpad_router_20220125.zip
for f in *.zip; do unzip $f; done

cd ..
python $basepath/cc2538-bsl.py -evw -p /dev/ttyUSB$3 \
  --bootloader-sonoff-usb  $basepath/$1/*$2*.hex

cd /config
rm -rf $basepath