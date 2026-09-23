## Added

- S05 PHEV sensor support: fuel level, fuel range and fuel tank capacity for plug-in hybrid vehicles.
- Read-only digital key support detection in the SDK: the phone key scheme (CA / ICCE / Honor) and the per-vehicle function authorizations, with no Home Assistant entities yet.

## Fixed

- The DC charging gun sensor no longer reports the cable as connected when it is unplugged.

## Removed

- The option to send the `X-Tsp-Timestamp` diagnostic header; the client no longer sends it.
