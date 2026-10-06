# Average vs marginal by region (generated)

Location-based average intensity (Google, 2024) answers *how clean is the electricity here?* Annual marginal intensity (GSF Real Time Cloud, WattTime-derived) answers *what does one more kWh here cause?* Joule Thief reports the first and decides on the second — and only claims savings for load moved into surplus hours, where the marginal kWh is renewable that would be curtailed.

| Region | City | Google CFE | Avg gCO₂/kWh | Marginal gCO₂/kWh (annual) | Marginal ÷ average |
|---|---|---:|---:|---:|---:|
| `us-east1` | Moncks Corner | 31% | 576 | 728 | 1.3× |
| `us-west1` | The Dalles | 87% | 79 | 427 | 5.4× |
| `northamerica-northeast1` | Montréal | 99% | 5 | 462 | 84.4× |
| `europe-west2` | London | 79% | 106 | 428 | 4.0× |
| `europe-north1` | Hamina | 98% | 39 | 785 | 20.0× |
| `europe-southwest1` | Madrid | 87% | 89 | 370 | 4.2× |
| `europe-west4` | Eemshaven | 83% | 209 | 487 | 2.3× |
| `europe-west1` | St. Ghislain | 84% | 103 | 411 | 4.0× |
| `europe-north2` | Stockholm | 100% | 3 | — | — |

Reading: Montréal and Finland look almost carbon-free on average, but extra demand there is met on the margin by generation (or lost exports) that is far dirtier. Average-based scheduling would call any hour there 'clean'; marginal-based dispatch waits for genuine surplus.
