# Local printer providers

UFM's printer contract is manufacturer-neutral. Current local adapters provide
**read-only monitoring** for:

- **OctoPrint**: OctoPrint-compatible printers, including devices from different
  manufacturers that expose its API.
- **Moonraker**: Klipper-based printers that expose Moonraker's HTTP API.
- **Bambu Lab LAN Mode**: read-only P1-series-style MQTT telemetry on the local
  network, including print state, progress, temperatures, and AMS tray identity
  metadata when the printer publishes it.

These adapters report connection health, current job state, progress where
available, and temperatures. The desktop can request a one-time snapshot and
shows AMS/feed-system slot counts where available. They do not control the
printer, configure AMS hardware, identify physical spools, or write consumption
to inventory. Filament
usage reported by Moonraker remains an estimate and is not yet evidence accepted
by UFM's accounting ledger. File names are not treated as unique print-run IDs:
reprints require a separate durable lifecycle identity before accounting can use
them.

Bambu LAN Mode requires LAN Mode enabled, the printer's local IP address, serial
number, and access code. See Bambu Lab's [LAN Mode guide](https://wiki.bambulab.com/en/knowledge-sharing/enable-lan-mode)
and the community integration's [LAN setup reference](https://docs.page/greghesp/ha-bambulab/setup)
for where to find those values. In UFM, choose **Add printer → Bambu Lab (LAN)**.
After finding the printer on the LAN, **Autofill from Bambu Studio** can read
the matching local Studio profile. UFM matches the serial number in the printer's
TLS certificate to Studio's saved IP and access-code entries; it imports a model
only when Studio has one unambiguous model selection. The access code stays
masked and is stored in the OS credential store only after the connection test
succeeds.

The first import displays the printer certificate's SHA-256 fingerprint and asks
for explicit trust. The imported issuer certificate is used for normal TLS
certificate-chain validation, and UFM additionally pins the exact leaf
certificate fingerprint before MQTT authentication is sent. The printer's
certificate does not include an IP subject alternative name, so the pin replaces
only hostname matching for this saved device; TLS certificate-chain validation
remains enabled. If the certificate changes, the connection fails closed and
requires a new explicit import/trust. Manually selected CA files keep standard
hostname verification. UFM reuses HaspelSync's Bambu MQTT settings (`bblp`,
port 8883, `device/{serial}/report`, and the `pushall` status request), but does
not copy its disabled TLS certificate verification. There is no insecure
certificate-verification bypass.
Bambu's MQTT reports may identify AMS trays and RFID/tag identifiers, but UFM
does not infer a spool mapping or remaining grams from those fields.

OctoPrint and Moonraker endpoints must be plain HTTP URLs on a literal loopback,
private-LAN, or link-local IP address. `localhost` is normalized to loopback.
DNS names, public IPs, HTTPS endpoints, redirects, and URL-embedded credentials
are rejected. Bambu uses local MQTT/TLS on port 8883, requires a literal local IP,
and validates certificates. OctoPrint API keys, Moonraker bearer
tokens, and Bambu access codes are accepted as `SecretValue`s and kept in the OS
secret store, never in settings, database rows, command-line arguments, or logs.

The desktop shell can add OctoPrint, Moonraker, and Bambu LAN Mode connections,
test the local endpoint before saving, list configured printers, and request a
one-time live status snapshot. Credentials are stored in the native OS credential store; only the
credential reference and local host/port are written to SQLite. An unavailable
credential store prevents saving rather than falling back to plaintext. The
setup and adapters are covered by local fixture tests and the Studio-import,
pinned-TLS path has been exercised against a physical Bambu P1S. The UI does not
initiate a Bambu connection automatically: first verify that concurrent local MQTT monitoring is
acceptable for the printer while another app is connected, and avoid first
connection testing during a print unless the user accepts possible device/app
connection interference.

To remove a connection, select its printer and choose **Remove printer**. UFM
asks for confirmation, deletes the connection profile and OS-stored credential,
and disables the printer record. Print history and other records that reference
the printer remain intact.

On Windows, **Find printers on local network** is an explicit, user-confirmed
discovery action. It selects the primary private IPv4 LAN and checks at most 256
addresses, on the standard OctoPrint (80), Moonraker (7125), and Bambu MQTT/TLS
(8883) ports only. OctoPrint and Moonraker candidates are identified by their
read-only API response where possible; an authorization response is marked
unverified. An open port 8883 is only a possible Bambu device, not proof of
identity. Discovery sends no credentials, does not send printer-control
commands, and never saves a candidate automatically. Choosing a result only
prefills the ordinary setup form; the user must verify and save it there. For Bambu,
the separate Studio import matches certificate serial, saved IP, and profile; the
user must explicitly approve the displayed certificate fingerprint before the
access code is used.

This is monitoring-only support, not full printer-management support: providers
are not yet polled by a durable desktop worker, and the shell does not yet expose
full feed-slot configuration or AMS-to-spool mapping. Automatic stock
deduction remains disabled until durable print identity, the finalization kernel,
replay/crash tests, and a physical end-to-end acceptance run are complete.
