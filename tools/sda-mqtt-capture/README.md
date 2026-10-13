# SDA MQTT capture helper

Small, self-contained kit to capture the Deepal app's traffic to the SDA broker
(`prod-appmq.sda.changanauto.sg:8883`) and to the app HTTP endpoints around it. Regular HTTP
proxies cannot show the MQTT connection, and the remote-control command codes travel **encrypted**
inside the MQTT `sers` field, so the kit decodes them locally and writes shareable logs.

> Looking for something simpler first? The [broker probe](../sda-mqtt-probe/README.md) runs on your
> computer with no phone, no mitmproxy and no certificate, and answers how the SDA broker session
> works (identity, topics, login exchange). Use this capture kit when the command codes themselves
> are needed.

## What you need

- A Mac with [mitmproxy](https://mitmproxy.org/) installed: `brew install mitmproxy`
  (or `pipx install mitmproxy`). mitmproxy already brings the `cryptography` dependency the decoder
  needs.
- The iPhone with the Deepal app and, for WireGuard mode, the free **WireGuard** app.

This helper is **not distributed with the HACS integration**: ask for it in the tracking issue
(it lives under `tools/`, outside the published package).

## Quick start

```bash
cd sda-mqtt-capture
./capture.sh
```

1. mitmproxy prints a WireGuard configuration: import it into the WireGuard iOS app and activate
   the tunnel.
2. Open `https://mitm.it` in Safari on the iPhone and install/trust the mitmproxy CA (Settings →
   General → VPN & Device Management, and then Settings → General → About → Certificate Trust
   Settings).
3. In the Deepal app, with **Bluetooth off**, do one **lock** and one **unlock** (and, if you can,
   one AC on/off), waiting a few seconds between them.
4. Stop mitmproxy with `Ctrl-C`.

If the app already honours the iOS Wi-Fi proxy, the simpler mode works too:

```bash
MODE=proxy ./capture.sh
```

## What to send back

**One file**, from the `capture/` directory: `mqtt-transcript.log`, plus `http-transcript.log` if it
was written. Skim them first: they must not contain your number plate, your car's location, your
tokens or your PIN — if any of those show up, tell us before sending.

Do **not** send `mqtt-raw.log`: it is off by default and it is only meant for your own machine.

## When it decodes nothing

The command codes are AES-encrypted with a per-session `secretKey` that the broker returns in the
login response. The kit reads it **in memory** as the capture runs and decrypts every `sers` blob it
sees, so `mqtt-transcript.log` shows a `sers_decoded` list with the `service_code` and
`command_code` of each action. Notes:

- If the transcript says `<unavailable: no secretKey captured yet>`, the login response was not seen
  (start the capture *before* opening the app) or this broker does not use the key exchange. Send
  the capture anyway: that answer alone is valuable.
- If it says `secretKey captured (N chars)`, decoding is active and the key never leaves your Mac.
- If a frame says `TLS handshake seen but not intercepted`, the CA is not trusted yet; repeat
  step 2 of the quick start.
- If the broker host never appears at all, tell us and we will try another capture path.

## Advanced: keeping the raw bytes locally

```bash
RAW=1 ./capture.sh
```

writes `mqtt-raw.log` with the hex of every TCP message **except** the CONNECT frame and the login
response, so the broker credentials and the `secretKey` never reach it. Keep that file local: it is
useful to re-decode a frame on your own machine, but it does hold the plaintext telemetry values it
captures (including the location and the plate), so treat it as sensitive and never attach it.

## Scope and cleanup

WireGuard mode intercepts **all** the TLS traffic of the iPhone while it is active, not only the
Deepal app. This kit only writes the Deepal MQTT brokers and the allowlisted Deepal HTTP paths, but
the tunnel and the trusted CA are device-wide, so:

1. Prefer a spare iPhone if you have one.
2. When you are done: stop mitmproxy (`Ctrl-C`), turn the WireGuard tunnel off, delete the WireGuard
   configuration, and remove the mitmproxy CA profile in **Settings → General → VPN & Device
   Management** (plus **Certificate Trust Settings**).

## Privacy

`mqtt-transcript.log` and `http-transcript.log` never contain:

- tokens, authorization headers, cookies, the MQTT `secretKey` or the control PIN;
- the number plate, the vehicle location (`Lat`/`Lng`/…) or GPS/address fields;
- user, account, car, device or DID identifiers: they are replaced by a stable
  `<did:1a2b3c4d>`-style tag so messages can still be correlated without revealing the value.

Service codes, command codes, decoded service parameters, message types and topic shapes are kept
readable on purpose: they are the evidence the maintainer needs.
