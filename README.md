# Home Assistant Greenchoice Sensor
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)

This is a Home Assistant custom component (sensor) that connects to the Greenchoice API to retrieve current usage data (daily meter data).

The sensor will check every hour if a new reading can be retrieved but Greenchoice practically only gives us one reading a day over this API. The reading is also delayed by 1 or 2 days (this seems to vary). The sensor will give you the date of the reading as an attribute.

### Install:

[//]: # (1. Search for 'greenchoice' in [HACS]&#40;https://hacs.xyz/&#41;. )

[//]: # (    *OR*)
1. Place the 'greenchoice' folder in your 'custom_compontents' directory if it exists or create a new one under your config directory.
2. Add your username and password to the secrets.yaml:

```YAML
greenchoicepass: your_secret_password
greenchoiceuser: your@user.name
```

3. Restart Home Assistant to make it load the integration
3. Finally add the component to your configuration.yaml, an example of a proper config entry:

```YAML
sensor:
  - platform: greenchoice
    name: meterstanden
    password: !secret greenchoicepass
    username: !secret greenchoiceuser
```
