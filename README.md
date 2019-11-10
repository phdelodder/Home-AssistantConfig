# Home Assistant Configuration

## About

Configuration files for [Home Assistant](https://home-assistant.io).

## Continuous Integration

Using a selfhosted gitlab vm and a selfhosted gitlab runner. Resource used for for my setup:

- [Continuous Integration for Home Assistant, ESPHome and AppDaemon](https://webworxshop.com/continuous-integration-for-home-assistant-esphome-and-appdaemon/)
- [Frenck's Home Assistant Configuration](https://github.com/frenck/home-assistant-config)

The CI is configured to do 3 steps:

- preflight, validation of the files
  - shellcheck
  - yamllint
  - jsonlint
  - markdownlint
- Check, validating the config against HA it self
  - Current version
  - Release candidate
  - Development
- Deployment, deploys pulls the latest updates on the remote server using SSH. This is only done when yaml files are changed.

## Custom Components

- [HACS](https://hacs.xyz/)
- [Variable](https://github.com/rogro82/hass-variables),
   using to do the installation and maintance
- [HP Printer](https://github.com/elad-bar/ha-hpprinter),
   using to do the installation and maintance

## Themes

- [Clear Theme](https://community.home-assistant.io/t/clear-theme/100464)

## Python Scripts

This is all done through HACS

- [Shellies Discovery](https://github.com/bieniu/ha-shellies-discovery)

## Lovelace Plugins

This is all done through HACS

- Bar Card
- Button Card
- Config Template Card
- Group Card
- Mini Graph Card
- Mini Media Player
- Monster Card
- Travel Time Card
- Vertical Stack In Card

## Camera

For monitoring my drive way I'm using an Dahua 'DH-IPC-HDBW4431R-ZS'. Integration is done through [Motion Eye](https://github.com/ccrisan/motioneye).

Motion detection can be enable or disable using the Motion API, you can use switches.yaml file for example config. To remove the localhost limited of Motion API see [github comment](https://github.com/ccrisan/motioneye/issues/800#issuecomment-453689160).
