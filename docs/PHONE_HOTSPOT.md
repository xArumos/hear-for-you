# PHONE_HOTSPOT.md — test the mic on a phone over a private hotspot

For an AI agent (or a person) who needs the real app, with a working microphone, on a phone. Tested Oct 24–25 on
P1's Linux laptop (Vite 5.4.21, Node 22.23.1) with the phone on the same private Wi-Fi.

## Why this setup

- Browsers only allow the microphone on `https://` pages or on `localhost`. A phone opening
  `http://<laptop-ip>:5173` sees the UI, but Listen and Teach can't get the mic.
- Fix: serve the Vite dev server over HTTPS with a short-lived self-signed certificate for the laptop's IP.
- Use a **private network only**: the phone's hotspot, or home Wi-Fi. The dev server answers everyone on the
  network and the app has no login, so on school or venue Wi-Fi anyone there could use the app, delete sounds and
  spend the Gemini quota (the detect cap is global, so a stranger's traffic gives *you* 429s). Venue Wi-Fi also
  often blocks device-to-device traffic, so the phone may not reach the laptop at all.
- Don't use a public tunnel (ngrok, `cloudflared`, which `SETUP.md` §6 mentions) for the demo unless the team accepts
  that the app is then on the open internet with no login.
- Simplest alternative: demo in the **laptop's** browser at `http://localhost:5173`. The mic works on localhost with
  no HTTPS, no certificate and no network exposure.

## Rules for agents

- **Don't edit `web/`** (P2 owns it) or add a dependency such as `@vitejs/plugin-basic-ssl`. Keep the HTTPS config
  and certificate **outside the repo** (your scratchpad, or `~/hfy-https/`). Never commit a key or certificate.
- Never print or read `api/.env`.
- Tell the human the exact `https://` URL, that a certificate warning appears once, and how to stop everything.

## Steps

### 1. Join the hotspot and find the laptop's IP

Turn on the phone's hotspot and connect the laptop to it. Then:

```bash
ip -4 -o addr show scope global | awk '{print $2, $4}'
```

Use the address on the Wi-Fi interface (e.g. `wlan0`). An iPhone hotspot usually gives `172.20.10.x`; Android varies.
Below, `LAPTOP_IP` is that address without the `/24`.

### 2. Make a certificate for that IP

```bash
DIR=~/hfy-https            # or your scratchpad; anywhere outside the repo
mkdir -p "$DIR"
openssl req -x509 -newkey rsa:2048 -nodes -days 7 \
  -keyout "$DIR/key.pem" -out "$DIR/cert.pem" \
  -subj "/CN=Hear For You dev" -addext "subjectAltName=IP:LAPTOP_IP,DNS:localhost"
```

The certificate covers one IP only. If the laptop's IP changes (another network, hotspot restarted), redo this step.

### 3. Write the HTTPS Vite config (outside the repo)

`$DIR/vite.https.config.mjs`, with absolute paths filled in:

```js
// Temporary HTTPS dev server for phone mic testing. Same as web/vite.config.ts, plus a self-signed cert.
// No React plugin (it can't resolve its helpers from outside web/): JSX compiles with esbuild, no hot reload.
import fs from 'node:fs';

const dir = '/home/<user>/hfy-https';

export default {
  root: '/home/<user>/dev/hear-for-you/web',
  esbuild: { jsx: 'automatic' },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    https: { key: fs.readFileSync(`${dir}/key.pem`), cert: fs.readFileSync(`${dir}/cert.pem`) },
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true, secure: false } },
  },
};
```

Gotchas this config already handles:
- Importing `@vitejs/plugin-react` from a config outside `web/` fails at request time with
  `Cannot find package 'react-refresh'`. Leave the plugin out and set `esbuild.jsx = 'automatic'`
  (`web/tsconfig.app.json` uses `react-jsx`; without the setting the browser gets "React is not defined").
- `root` must point at `web/`, and the `/api` proxy must match `web/vite.config.ts`.
- `strictPort` makes a busy port fail loudly instead of moving to another port the phone doesn't know about.

### 4. Start the API, then the HTTPS web server

Two background processes. Stop any plain `npm run dev` on port 5173 first.

```bash
cd api && uv run uvicorn app.main:app --port 8000      # listens on 127.0.0.1 only; reached through the proxy
```

```bash
cd web && npx vite --config ~/hfy-https/vite.https.config.mjs
```

- `web/node_modules` must exist (`npm ci` in `web/`).
- On P1's laptop Node isn't on `PATH`; it's in the Nix store. Find it with
  `ls -d /nix/store/*nodejs-22*/bin/npm` and prefix the command with
  `PATH=/nix/store/<hash>-nodejs-22.<x>/bin:$PATH`. Use the full `nodejs-22…` build; the `nodejs-slim` ones have no npm.

### 5. Check it from the laptop before telling the human

```bash
B=https://LAPTOP_IP:5173
curl -sk -o /dev/null -w "page %{http_code}\n" $B                 # 200
curl -sk $B/api/health                                            # {"ok":true,...}
curl -sk $B/src/App.tsx | grep -c jsx                             # > 0: TSX compiled, not an error page
```

Also check the Vite output for `Internal server error` lines.

### 6. On the phone

1. Open `https://LAPTOP_IP:5173` (**https**, with the port).
2. Accept the certificate warning once:
   - **iPhone (Safari):** Show Details → visit this website → confirm. Use Safari, not "Add to Home Screen"
     (Wake Lock doesn't work there).
   - **Android (Chrome):** Advanced → Proceed to LAPTOP_IP (unsafe).
3. Allow the microphone when Listen or Teach asks.

### 7. If the page doesn't load on the phone

- **Firewall:** P1's laptop runs `ufw`. Changing the firewall is the human's call. Suggest they run, scoped to the
  hotspot subnet:
  `! sudo ufw allow from <subnet>/24 to any port 5173 proto tcp`, and afterwards
  `! sudo ufw delete allow from <subnet>/24 to any port 5173 proto tcp`.
- **Wrong network:** the phone itself is the hotspot, so it's always on that network. Make sure the laptop joined it.
- **Old URL or certificate:** the IP changed; redo steps 1–2 and restart the web server.

## Stopping

Stop both background processes (find PIDs with `ps -eo pid,comm,args | awk '$2 ~ /uvicorn|node/'` in a separate
command, then `kill <pid>`), and check `ss -ltn | grep -E ':8000|:5173'` prints nothing. Delete `~/hfy-https/` when
done; the certificate expires in 7 days anyway.
