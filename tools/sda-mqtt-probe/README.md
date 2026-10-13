# SDA MQTT broker probe

A single Python script that runs **on your computer** and answers how the SDA
broker session works for your car. It needs no phone, no mitmproxy and no
certificate to install: just Python and the SDK from this repository.

It is the easy first step. The [capture kit](../sda-mqtt-capture/README.md) is
still the only way to read the *command codes* the app sends (they travel
encrypted inside the MQTT `sers` field), but this probe already answers most of
the open questions and costs you nothing to run.

## What it does

1. Logs in with your account (the same secondary account Home Assistant uses).
2. Asks the SDA gateway for the broker configuration the app uses
   (`get-mqtt-server-config?carId=`) and for the `vot-auth` auth token.
3. Connects to the broker over TLS and tries the CONNECT identities in order,
   reporting which one the broker accepts and why the others are rejected.
4. Subscribes to the topics the account is allowed to use and reports the
   SUBACK result per topic (granted / not authorized / wildcards not supported).
5. Listens for a while and logs everything the broker sends, with tokens,
   passwords, identifiers, plate and location masked. Any encrypted `sers` list
   it can decode is decoded locally.

It **never publishes a control command**. The only message it can send is the
`loginout` exchange, and only with `--allow-login`, because opening a session
may kick the app on your phone.

## What it answers

- the `authType 2` identity: which client id / username / password the broker
  accepts (the question the SDK cannot guess);
- which topics this account may subscribe to, and whether wildcard
  subscriptions are allowed;
- whether the broker delivers the app's own frames to another session of the
  same account (if it does, pressing unlock in the app while the probe listens
  can hand us the command codes without any phone setup);
- whether the `loginout` exchange works and returns a `secretKey`.

## What it does not answer

- the exact `service_code`/`command_code` of lock, unlock and climate if the
  broker does **not** fan out the app's frames to this session, or if the app's
  `sers` is encrypted with a key this session does not have. For those, use the
  capture kit.

## Requirements

- Python 3.10 or newer.
- The SDK from this repository (no install needed: the script adds it to the
  path).

## Usage

```bash
cd tools/sda-mqtt-probe
DEEPAL_EMAIL=you@example.com DEEPAL_PASSWORD=secret \
    python probe.py --country AU --environment release_ase
```

Useful options:

| Option | Meaning |
| --- | --- |
| `--list-vehicles` | print the account vehicles (masked ids) and exit |
| `--car-id <id>` | probe a specific vehicle (default: the `SDA-MQTT` one) |
| `--seconds 90` | listen window (default 90 s) |
| `--allow-login` | publish the `loginout` exchange (may kick the app session) |
| `--wildcard` | also subscribe to `$vdp/<did>/#` to observe the app's frames |
| `--log sda-probe.log` | redacted log file (default `sda-probe.log`) |

Credentials come from the environment: `DEEPAL_EMAIL` + `DEEPAL_PASSWORD`, or
`DEEPAL_EMAIL` + `DEEPAL_CODE` (email verification code), or a pair of saved
tokens `DEEPAL_ACCESS_TOKEN` + `DEEPAL_REFRESH_TOKEN`. Nothing is written to
disk except the redacted log.

### The interesting run

```bash
DEEPAL_EMAIL=… DEEPAL_PASSWORD=… python probe.py \
    --country AU --environment release_ase --allow-login --wildcard --seconds 120
```

While it says `Listening`, press **lock** and then **unlock** in the app (with
Bluetooth off). If the broker delivers the app's frames to this session, the log
shows the command topics and, when the `secretKey` is available, the decoded
`sers` with the command codes.

## What to send back

`tools/sda-mqtt-probe/sda-probe.log` (or the path you passed to `--log`). Skim
it first: it must not contain your tokens, your plate, your car's location or
your account ids.

## Notes and safety

- The script talks to the production gateway and broker with your account. It
  makes a handful of HTTP calls and one MQTT session; it never sends a command.
- `--allow-login` may sign the phone app out (the broker usually keeps one
  session per account). If that happens, just open the app again.
- Everything it writes is masked with the SDK redactor plus explicit masking of
  `secretKey`, `userName`, `password`, `clientId`, DIDs and car ids.
