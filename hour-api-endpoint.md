## URL:
https://mijn.greenchoice.nl/api/v2/customers/{customer_number}/agreements/{agreement_id}/consumptions?interval=Hour&start=2025-12-28&end=2025-12-29

This call is performed on 2025-12-29, so it will return data for 2025-12-28.
You can only import data of yesterday and earlier. Today's data is not available yet.

## Response
```json
{
    "interval": "Hour",
    "start": "2025-12-28T00:00:00",
    "end": "2025-12-29T00:00:00",
    "consumptionCosts": [
        {
            "consumedOn": "2025-12-28T00:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 0.49,
                "deliveryNormalCosts": 0.11022,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": 0,
                "feedInNormalCompensation": 0.00000,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 0.49,
                "totalDeliveryCosts": 0.11022,
                "totalFeedInConsumption": 0,
                "totalFeedInCompensation": 0.00000,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": 0.49,
                "netElectricityCosts": 0.10455,
                "netCosts": 0.10455
            }
        },
        {
            "consumedOn": "2025-12-28T01:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 0.222,
                "deliveryNormalCosts": 0.04994,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": 0,
                "feedInNormalCompensation": 0.00000,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 0.222,
                "totalDeliveryCosts": 0.04994,
                "totalFeedInConsumption": 0,
                "totalFeedInCompensation": 0.00000,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": 0.222,
                "netElectricityCosts": 0.04427,
                "netCosts": 0.04427
            }
        },
        {
            "consumedOn": "2025-12-28T02:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 0.074,
                "deliveryNormalCosts": 0.01665,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": 0,
                "feedInNormalCompensation": 0.00000,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 0.074,
                "totalDeliveryCosts": 0.01665,
                "totalFeedInConsumption": 0,
                "totalFeedInCompensation": 0.00000,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": 0.074,
                "netElectricityCosts": 0.01098,
                "netCosts": 0.01098
            }
        },
        {
            "consumedOn": "2025-12-28T03:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 0.08,
                "deliveryNormalCosts": 0.01800,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": 0,
                "feedInNormalCompensation": 0.00000,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 0.08,
                "totalDeliveryCosts": 0.01800,
                "totalFeedInConsumption": 0,
                "totalFeedInCompensation": 0.00000,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": 0.08,
                "netElectricityCosts": 0.01233,
                "netCosts": 0.01233
            }
        },
        {
            "consumedOn": "2025-12-28T04:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 0.069,
                "deliveryNormalCosts": 0.01552,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": 0,
                "feedInNormalCompensation": 0.00000,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 0.069,
                "totalDeliveryCosts": 0.01552,
                "totalFeedInConsumption": 0,
                "totalFeedInCompensation": 0.00000,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": 0.069,
                "netElectricityCosts": 0.00985,
                "netCosts": 0.00985
            }
        },
        {
            "consumedOn": "2025-12-28T05:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 0.083,
                "deliveryNormalCosts": 0.01867,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": 0,
                "feedInNormalCompensation": 0.00000,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 0.083,
                "totalDeliveryCosts": 0.01867,
                "totalFeedInConsumption": 0,
                "totalFeedInCompensation": 0.00000,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": 0.083,
                "netElectricityCosts": 0.01300,
                "netCosts": 0.01300
            }
        },
        {
            "consumedOn": "2025-12-28T06:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 0.535,
                "deliveryNormalCosts": 0.12034,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": 0,
                "feedInNormalCompensation": 0.00000,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 0.535,
                "totalDeliveryCosts": 0.12034,
                "totalFeedInConsumption": 0,
                "totalFeedInCompensation": 0.00000,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": 0.535,
                "netElectricityCosts": 0.11467,
                "netCosts": 0.11467
            }
        },
        {
            "consumedOn": "2025-12-28T07:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 1.451,
                "deliveryNormalCosts": 0.32639,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": 0,
                "feedInNormalCompensation": 0.00000,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 1.451,
                "totalDeliveryCosts": 0.32639,
                "totalFeedInConsumption": 0,
                "totalFeedInCompensation": 0.00000,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": 1.451,
                "netElectricityCosts": 0.32072,
                "netCosts": 0.32072
            }
        },
        {
            "consumedOn": "2025-12-28T08:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 1.938,
                "deliveryNormalCosts": 0.43593,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": 0,
                "feedInNormalCompensation": 0.00000,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 1.938,
                "totalDeliveryCosts": 0.43593,
                "totalFeedInConsumption": 0,
                "totalFeedInCompensation": 0.00000,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": 1.938,
                "netElectricityCosts": 0.43026,
                "netCosts": 0.43026
            }
        },
        {
            "consumedOn": "2025-12-28T09:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 0.976,
                "deliveryNormalCosts": 0.21954,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": -0.003,
                "feedInNormalCompensation": -0.00067,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 0.976,
                "totalDeliveryCosts": 0.21954,
                "totalFeedInConsumption": -0.003,
                "totalFeedInCompensation": -0.00067,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": 0.973,
                "netElectricityCosts": 0.21320,
                "netCosts": 0.21320
            }
        },
        {
            "consumedOn": "2025-12-28T10:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 0.083,
                "deliveryNormalCosts": 0.01867,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": -0.509,
                "feedInNormalCompensation": -0.11449,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 0.083,
                "totalDeliveryCosts": 0.01867,
                "totalFeedInConsumption": -0.509,
                "totalFeedInCompensation": -0.11449,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": -0.426,
                "netElectricityCosts": -0.10149,
                "netCosts": -0.10149
            }
        },
        {
            "consumedOn": "2025-12-28T11:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 0.001,
                "deliveryNormalCosts": 0.00022,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": -0.853,
                "feedInNormalCompensation": -0.19187,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 0.001,
                "totalDeliveryCosts": 0.00022,
                "totalFeedInConsumption": -0.853,
                "totalFeedInCompensation": -0.19187,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": -0.852,
                "netElectricityCosts": -0.19732,
                "netCosts": -0.19732
            }
        },
        {
            "consumedOn": "2025-12-28T12:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 0.12,
                "deliveryNormalCosts": 0.02699,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": -0.472,
                "feedInNormalCompensation": -0.10617,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 0.12,
                "totalDeliveryCosts": 0.02699,
                "totalFeedInConsumption": -0.472,
                "totalFeedInCompensation": -0.10617,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": -0.352,
                "netElectricityCosts": -0.08485,
                "netCosts": -0.08485
            }
        },
        {
            "consumedOn": "2025-12-28T13:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 0.01,
                "deliveryNormalCosts": 0.00225,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": -0.753,
                "feedInNormalCompensation": -0.16938,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 0.01,
                "totalDeliveryCosts": 0.00225,
                "totalFeedInConsumption": -0.753,
                "totalFeedInCompensation": -0.16938,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": -0.743,
                "netElectricityCosts": -0.17280,
                "netCosts": -0.17280
            }
        },
        {
            "consumedOn": "2025-12-28T14:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 0.27,
                "deliveryNormalCosts": 0.06073,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": -0.204,
                "feedInNormalCompensation": -0.04589,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 0.27,
                "totalDeliveryCosts": 0.06073,
                "totalFeedInConsumption": -0.204,
                "totalFeedInCompensation": -0.04589,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": 0.066,
                "netElectricityCosts": 0.00917,
                "netCosts": 0.00917
            }
        },
        {
            "consumedOn": "2025-12-28T15:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 1.035,
                "deliveryNormalCosts": 0.23281,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": -0.009,
                "feedInNormalCompensation": -0.00202,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 1.035,
                "totalDeliveryCosts": 0.23281,
                "totalFeedInConsumption": -0.009,
                "totalFeedInCompensation": -0.00202,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": 1.026,
                "netElectricityCosts": 0.22512,
                "netCosts": 0.22512
            }
        },
        {
            "consumedOn": "2025-12-28T16:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 0.761,
                "deliveryNormalCosts": 0.17118,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": 0,
                "feedInNormalCompensation": 0.00000,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 0.761,
                "totalDeliveryCosts": 0.17118,
                "totalFeedInConsumption": 0,
                "totalFeedInCompensation": 0.00000,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": 0.761,
                "netElectricityCosts": 0.16551,
                "netCosts": 0.16551
            }
        },
        {
            "consumedOn": "2025-12-28T17:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 1.613,
                "deliveryNormalCosts": 0.36283,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": 0,
                "feedInNormalCompensation": 0.00000,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 1.613,
                "totalDeliveryCosts": 0.36283,
                "totalFeedInConsumption": 0,
                "totalFeedInCompensation": 0.00000,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": 1.613,
                "netElectricityCosts": 0.35716,
                "netCosts": 0.35716
            }
        },
        {
            "consumedOn": "2025-12-28T18:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 1.571,
                "deliveryNormalCosts": 0.35338,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": 0,
                "feedInNormalCompensation": 0.00000,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 1.571,
                "totalDeliveryCosts": 0.35338,
                "totalFeedInConsumption": 0,
                "totalFeedInCompensation": 0.00000,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": 1.571,
                "netElectricityCosts": 0.34771,
                "netCosts": 0.34771
            }
        },
        {
            "consumedOn": "2025-12-28T19:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 1.194,
                "deliveryNormalCosts": 0.26858,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": 0,
                "feedInNormalCompensation": 0.00000,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 1.194,
                "totalDeliveryCosts": 0.26858,
                "totalFeedInConsumption": 0,
                "totalFeedInCompensation": 0.00000,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": 1.194,
                "netElectricityCosts": 0.26291,
                "netCosts": 0.26291
            }
        },
        {
            "consumedOn": "2025-12-28T20:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 1.01,
                "deliveryNormalCosts": 0.22719,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": 0,
                "feedInNormalCompensation": 0.00000,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 1.01,
                "totalDeliveryCosts": 0.22719,
                "totalFeedInConsumption": 0,
                "totalFeedInCompensation": 0.00000,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": 1.01,
                "netElectricityCosts": 0.22152,
                "netCosts": 0.22152
            }
        },
        {
            "consumedOn": "2025-12-28T21:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 0.165,
                "deliveryNormalCosts": 0.03711,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": 0,
                "feedInNormalCompensation": 0.00000,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 0.165,
                "totalDeliveryCosts": 0.03711,
                "totalFeedInConsumption": 0,
                "totalFeedInCompensation": 0.00000,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": 0.165,
                "netElectricityCosts": 0.03144,
                "netCosts": 0.03144
            }
        },
        {
            "consumedOn": "2025-12-28T22:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 0.501,
                "deliveryNormalCosts": 0.11269,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": 0,
                "feedInNormalCompensation": 0.00000,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 0.501,
                "totalDeliveryCosts": 0.11269,
                "totalFeedInConsumption": 0,
                "totalFeedInCompensation": 0.00000,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": 0.501,
                "netElectricityCosts": 0.10702,
                "netCosts": 0.10702
            }
        },
        {
            "consumedOn": "2025-12-28T23:00:00",
            "electricity": {
                "deliveryLowConsumption": null,
                "deliveryLowCosts": null,
                "deliveryNormalConsumption": 0.825,
                "deliveryNormalCosts": 0.18557,
                "feedInLowConsumption": null,
                "feedInLowCompensation": null,
                "feedInNormalConsumption": 0,
                "feedInNormalCompensation": 0.00000,
                "variableFeedInCosts": null,
                "fixedDeliveryCosts": 0.01276,
                "gridOperatorCosts": 0.05408,
                "reductionEnergyTax": -0.07251,
                "totalDeliveryConsumption": 0.825,
                "totalDeliveryCosts": 0.18557,
                "totalFeedInConsumption": 0,
                "totalFeedInCompensation": 0.00000,
                "totalFeedInCosts": null,
                "totalFixedCosts": -0.00567
            },
            "gas": null,
            "windVangers": null,
            "net": {
                "netElectricityConsumption": 0.825,
                "netElectricityCosts": 0.17990,
                "netCosts": 0.17990
            }
        }
    ],
    "total": {
        "consumedOn": "2025-12-28T00:00:00",
        "electricity": {
            "deliveryLowConsumption": null,
            "deliveryLowCosts": null,
            "deliveryNormalConsumption": 15.077,
            "deliveryNormalCosts": 3.39140,
            "feedInLowConsumption": null,
            "feedInLowCompensation": null,
            "feedInNormalConsumption": -2.803,
            "feedInNormalCompensation": -0.63049,
            "variableFeedInCosts": null,
            "fixedDeliveryCosts": 0.30624,
            "gridOperatorCosts": 1.29792,
            "reductionEnergyTax": -1.74024,
            "totalDeliveryConsumption": 15.077,
            "totalDeliveryCosts": 3.39140,
            "totalFeedInConsumption": -2.803,
            "totalFeedInCompensation": -0.63049,
            "totalFeedInCosts": null,
            "totalFixedCosts": -0.13608
        },
        "gas": null,
        "windVangers": null,
        "net": {
            "netElectricityConsumption": 12.274,
            "netElectricityCosts": 2.62483,
            "netCosts": 2.62483
        }
    }
}
```