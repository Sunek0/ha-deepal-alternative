# Complete guide: secondary account and installing Deepal Alternative

Step-by-step guide to connect your Changan/Deepal car to Home Assistant with the
**Deepal Alternative** integration. It covers the whole process: from creating the secondary
account in the My Changan app to installing the integration with HACS and configuring it.

## Contents

1. [Why use a secondary account](#why-use-a-secondary-account)
2. [Prerequisites](#prerequisites)
3. [Part 1: secondary account in My Changan](#part-1-secondary-account-in-my-changan)
4. [Part 2: installing the integration](#part-2-installing-the-integration)
5. [Notes and troubleshooting](#notes-and-troubleshooting)

## Why use a secondary account

The integration signs in to the official My Changan platform. A single account cannot keep two
sessions active at once: if Home Assistant signs in with your main account, the mobile app may be
signed out, and signing in to the app again invalidates the Home Assistant session.

The recommended solution is to create a **secondary account**, share the car from the main account
and use only the secondary one in Home Assistant. That way your main account keeps working normally
on the phone.

## Prerequisites

- A compatible Deepal vehicle (S05, S07) linked to a My Changan account.
- Access to the **My Changan** app with the main account.
- A different email address or phone number for the secondary account.
- Home Assistant 2026.3.0 or later.
- [HACS](https://hacs.xyz/docs/use/download/download/) installed. If you do not have it yet, follow
  the official installation instructions at <https://hacs.xyz/docs/use/download/download/>.

## Part 1: secondary account in My Changan

### 1. Create the secondary account

1. Open the **My Changan** app and create a new account with an email address or a phone number
   different from your main account's.
2. Note down the credentials (email/phone and access code): these are the ones you will use in Home
   Assistant.

### 2. Share the vehicle from the main account

1. Sign out of the secondary account and sign in to the app with the **main account**.
2. Tap the **share** button on the main screen.
3. Invite the secondary account you just created, setting a permanent validity period.

### 3. Accept the access and create the control password

1. Sign out of the **main account** in the app and sign in with the **secondary account**.
2. Accept access to the shared car.
3. Go to the **personal center** (profile) and tap **My vehicle**.
4. Select the shared car.
5. Tap **Vehicle control password** and create a password (PIN). Note it down: this is the PIN Home
   Assistant will ask for the door, window and trunk commands.

> If you cannot find that option in your app version, try lowering the windows from the app: it will
> ask you to create the control PIN. Create it and check that the command works.

### 4. Back to the main account

1. Sign out of the secondary account and sign in again with the **main account** on the phone.
2. The main account remains the vehicle owner; the secondary one is used only in Home Assistant.

## Part 2: installing the integration

### 5. Install HACS (if you do not have it yet)

HACS is Home Assistant's custom integration manager. If you do not have it installed yet, follow the
official guide: <https://hacs.xyz/docs/use/download/download/>. Once installed, the **HACS** tab
appears in the Home Assistant sidebar.

### 6. Add the repository to HACS

1. In Home Assistant, open the **HACS** tab.
2. Open the three-dot menu (⋮) in the top right corner and choose **Custom repositories**.
3. Paste the repository URL:
   `https://github.com/Sunek0/ha-deepal-alternative`
4. Under **Category**, select **Integration** and press **Add**.

### 7. Install Deepal Alternative and restart

1. In HACS, search for **Deepal Alternative** (you can use the tab's search box or the
   **Integrations** category).
2. Open the entry and press **Download**.
3. **Restart Home Assistant** to load the new integration.

### 8. Add the integration

1. Go to **Settings → Devices and services**.
2. Press **Add integration** and search for **Deepal Alternative**.
3. Under **Platform**, choose **International (Europe)** (the SDA (China) option is only for
   mainland-China accounts with an access token).
4. Under **Login method**, choose how your secondary account signs in:
   - **Email code**: a verification code is sent to the email address.
   - **Phone/SMS code**: a verification code is sent by SMS to the mobile phone.
5. Fill in the form fields:
   - **Sales country**: the country registered in your My Changan account (for example, Spain).
   - **Email** or **Mobile number** (without the country prefix) of the **secondary** account.
6. Wait for the verification code (email or SMS) and enter it in **Verification code**.
7. The integration validates the account and creates one device per vehicle. Done.

### 9. Save the remote control PIN

This step **is only needed** to use the signed commands (door lock, windows and trunk) and for Home
Assistant to create their entities:

1. Go to **Settings → Devices and services → Deepal Alternative**.
2. Press **Configure**.
3. Under **Remote control PIN**, enter the password you created in step 3 with the secondary
   account.
4. Save. The door, window and trunk entities appear on the car's device.

### 10. Check that it works

- Open the vehicle's device page: you should see the battery, range, charging and other telemetry
  sensors.
- Try a safe command (for example, turning on the lights or the climate) and confirm the car
  responds.
- The commands that depend on the PIN (doors, windows, trunk) are signed with the PIN you created
  with the secondary account; if they fail, recheck step 9.

## Notes and troubleshooting

- **I cannot control anything**: first check whether the official app can do it with the same
  account. The car sometimes refuses remote commands until it has been driven for a few minutes.
- **"Remote control PIN is not set" although I already saved the PIN**: the PIN was not created with
  the account Home Assistant uses. Sign in to the app with the secondary account, create the PIN
  (step 3) and save it again in the integration options.
- **Home Assistant asks to reauthenticate**: the session was invalidated from the app or another
  device. Sign in again; with the secondary account this is much less frequent.
- **Values look stale**: the car only reports telemetry while it is awake; the integration shows the
  last known reading until it reports again.
- **Warning**: unofficial project, not related to Changan Automobile. Remote commands act on the
  real car: make sure it is safe before using locks, windows, trunk, climate, lights or horn.
