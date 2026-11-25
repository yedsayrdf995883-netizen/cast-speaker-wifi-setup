# Cast speaker Wi-Fi setup from a computer

Puts a Google Cast speaker (JBL Link 10/20/300/500 and similar) on your Wi-Fi when the
current Google Home app no longer finds it during setup.

## You need

- A computer with Wi-Fi (Windows, macOS or Linux).
- Python 3.8 or newer. Nothing else to install.
- `cast_speaker_wifi_setup.py` from this folder.

## Steps

1. **Factory reset the speaker** and wait until it has restarted. On the JBL Link 500, hold
   the mic-mute button for about 15 seconds. The speaker then broadcasts its own open Wi-Fi
   network, named after the speaker (for example `JBL Link 500-xxxxxx`).
2. **Connect the computer's Wi-Fi to that network.** It has no password. "No internet" is
   expected.
3. **Run the script:**

   ```
   python cast_speaker_wifi_setup.py
   ```

4. Pick your home network from the list, type its password, and optionally give the speaker
   a name. The speaker joins within about a minute.
5. **Reconnect the computer to your home Wi-Fi.**

After that the speaker can be cast to from phones and Chrome on the same network, and the
Google Home app should offer to add it to your home.

## Options

| Option | Meaning |
|---|---|
| `--ssid NAME` | Home network to join; skips the menu |
| `--name NAME` | Name to give the speaker |
| `--host ADDR` | Speaker address on its setup network. Default `192.168.255.249`; if nothing answers there, the computer's gateway is tried automatically |
| `--dry-run` | Stop before any Wi-Fi details are sent |

## If it fails

- **"No speaker at 192.168.255.249"**: the computer is not on the speaker's network, or the
  speaker is not in setup mode. Reset it again and rejoin.
- **"The speaker did not get onto the Wi-Fi"**: usually a wrong password. Run again.
- **"Lost contact with the speaker after sending"**: the computer dropped off the setup
  network while the speaker switched over. If the speaker announces it is connected, it
  worked.
- **The speaker cannot see your network**: old speakers need 2.4 GHz or 5 GHz with WPA2. A
  WPA3-only or 6 GHz-only network will not show up.

## Privacy

The password is encrypted with the speaker's own public key before it is sent, and is never
stored or printed. The script talks only to the speaker.

## Status

Tested against a simulated speaker. The read-only half (status and network scan) is also
tested against a real JBL Link 500 on firmware 1.52. Sending Wi-Fi details to a real speaker
has not been confirmed yet.
