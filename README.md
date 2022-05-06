# Home Assistant Greenchoice Sensor
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)

This is a Home Assistant custom component (sensor) that connects to the Greenchoice API to retrieve current usage data (daily meter data).

The sensor will check every hour if a new reading can be retrieved but Greenchoice practically only gives us one reading a day over this API. The reading is also delayed by 1 or 2 days (this seems to vary). The sensor will give you the date of the reading as an attribute.

### Install:

[//]: # (1. Search for 'greenchoice' in [HACS]&#40;https://hacs.xyz/&#41;. )

[//]: # (    *OR*)
1. Place the 'greenchoice' folder in your 'custom_compontents' directory if it exists or create a new one under your config directory.
2. The Greenchoice API can theoretically have multiple contracts under one user account, so we need to figure out the ID for the contract. We can use the script `get-overeenkomsten.py` to list all contracts for our account as follows:
   1. Install this package using pip (`python3 -m pip install .`)
   2. Run the script using `python3 get-overeenkomsten.py` (while CD'ed into the root directory) or by double-clicking it (on Windows.)
   3. It will ask for your username and password, after entering these, your contracts will be shown.
3. Add the component to your configuration.yaml, an example of a proper config entry:

```YAML
sensor:
  - platform: greenchoice
    name: meterstanden
    password: !secret greenchoicepass
    username: !secret greenchoiceuser
    overeenkomst_id: !secret greenchoicecontract
```
