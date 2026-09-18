# Owner action required — USB debugging authorization

Device serial: `27211JEGR06194` (Pixel 6a / bluejay)

ADB currently reports: **unauthorized**

The Mac already captured a successful baseline earlier in this session, but the authorization prompt must be accepted again after `adb kill-server` / cable re-plug.

## Exact steps

1. Unlock the Pixel 6a.
2. When the **"Allow USB debugging?"** dialog appears, check **"Always allow from this computer"**.
3. Tap **Allow**.
4. If no dialog appears: disconnect USB-C, reconnect, unlock, then run on Mac:
   ```bash
   adb kill-server; adb start-server; adb devices -l
   adb shell echo ping
   ```
5. Confirm `adb devices -l` shows:
   ```text
   27211JEGR06194         device ... model:Pixel_6a ...
   ```
   (must say `device`, not `unauthorized`)

Then re-run:

```bash
make pixel-waike-full-pilot
```

Physical gates that remain false until re-authorized evidence is captured:
- `PIXEL_ACCESSIBILITY_MECHANICS_PASS`
- `PIXEL_WAIKE_OFFLINE_RESTART_RECONNECT_PASS`
- `PIXEL_WAIKE_STABILITY_PASS` (full 30-minute soak)
- Aggregate `WAIKE_ALL_CONTENT_ALL_ROLE_PIXEL_PILOT_PASS`

## Flaky auth observed

ADB briefly shows `device`, then flips to `unauthorized` on the next `adb shell` / screencap.
This usually means **"Always allow from this computer" was not checked**, or the RSA key prompt needs a fresh Allow after `adb kill-server`.

Please:

1. Revoke USB debugging authorizations on Pixel (Developer options → Revoke USB debugging authorizations).
2. Re-plug USB-C, unlock.
3. Accept the prompt with **Always allow from this computer** checked.
4. Confirm stable: `adb shell getprop ro.product.model` succeeds repeatedly.
