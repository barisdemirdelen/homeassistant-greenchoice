# Home Assistant Greenchoice Sensor

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)

This is a Home Assistant custom component that connects to the Greenchoice API to retrieve current usage data (daily meter data).

The integration will check every hour if a new reading can be retrieved but Greenchoice practically only gives us one reading a day over this API. The reading is also delayed by 1 or 2 days (this seems to vary). The sensors will give you the date of the reading as an attribute.

## Installation

### HACS Installation (Recommended)

1. Add this repository URL as a custom repository in HACS and label it as an integration
2. Install the "Greenchoice" integration via HACS
3. Restart Home Assistant
4. Go to **Settings** > **Devices & Services** > **Add Integration**
5. Search for "Greenchoice" and follow the configuration steps

### Manual Installation

1. Place the `greenchoice` folder in your `custom_components` directory
2. Restart Home Assistant
3. Go to **Settings** > **Devices & Services** > **Add Integration**
4. Search for "Greenchoice" and follow the configuration steps

## Configuration

The integration uses Home Assistant's config flow for easy setup through the UI.

### Basic Setup

1. Go to **Settings** > **Devices & Services**
2. Click **Add Integration** and search for "Greenchoice"
3. Enter your Greenchoice credentials:
   - **Email**: Your Greenchoice login email
   - **Password**: Your Greenchoice password
4. Select your contract address from the options. Optionally fill in:
   - **Sensor Name**: Custom name for this instance (optional, defaults to "Greenchoice")

### Multiple Contracts

You can add multiple Greenchoice integrations for different contracts or accounts:

1. Repeat the setup process for each contract
2. Use different names to distinguish between them (e.g., "House Energy", "Solar System")
3. Each integration will create its own set of sensors with the custom name as prefix

## Sensors Created

Each integration instance creates the following sensors:

### Electricity Consumption
- **Electricity Consumption Off Peak** (kWh) - Low tariff consumption
- **Electricity Consumption Normal** (kWh) - Normal/peak tariff consumption  
- **Electricity Consumption Total** (kWh) - Total electricity consumed

### Electricity Production/Feed-in
- **Electricity Feed In Off Peak** (kWh) - Low tariff feed-in to grid
- **Electricity Feed In Normal** (kWh) - Normal/peak tariff feed-in to grid
- **Electricity Feed In Total** (kWh) - Total electricity fed back to grid

### Electricity Pricing
- **Electricity Price Single** (€/kWh) - Single rate electricity price
- **Electricity Price Off Peak** (€/kWh) - Low tariff electricity price
- **Electricity Price Normal** (€/kWh) - Normal/peak tariff electricity price
- **Electricity Feed In Compensation** (€/kWh) - Compensation rate for fed-in electricity
- **Electricity Feed In Cost** (€/kWh) - Cost/fee for feeding electricity back

### Gas
- **Gas Consumption** (m³) - Gas consumption
- **Gas Price** (€/m³) - Gas price per cubic meter


All sensors include the reading date as an attribute and are automatically discovered by Home Assistant's Energy dashboard.

## Migration from YAML Configuration

If you're upgrading from the YAML-based version:

1. Remove the old YAML configuration from `configuration.yaml`
2. Restart Home Assistant
3. Add the integration through the UI as described above
4. Your historical data will be preserved if you use the same entity names

## Troubleshooting

- The integration logs to Home Assistant's default logger under the `greenchoice` domain

For issues or feature requests, please use the GitHub repository.
