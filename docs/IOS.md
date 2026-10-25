# iOS build and testing

The existing `web/` React app is bundled by Capacitor 8.5.3 into WKWebView;
there is no separate frontend. The website still uses `npm run dev` / `npm run build`.
The native display name is **HearAlert**, per the iOS request. Its provisional
bundle ID is **dev.hearforyou.app**; review it before signing/distribution.
No App Store upload, account enrollment or signing team is configured. The generated
app icon/splash are template assets and need distribution review.

## Requirements

Use Node 22 LTS and install full Xcode 26 or newer, its iOS SDK and a simulator.
Command Line Tools alone cannot compile/run this project. In Xcode Settings,
select the installed Xcode command-line tools. See the official
[environment setup](https://capacitorjs.com/docs/getting-started/environment-setup)
and [iOS workflow](https://capacitorjs.com/docs/ios).

This project was generated/synchronized on a Mac with Command Line Tools only.
It has not been compiled by Xcode or run in WKWebView/a simulator/on a phone.
Web tests cannot certify native microphone, networking or lifecycle behavior.

## Backend configuration

All Gemini calls and the API key remain in FastAPI. A backend origin is public
configuration compiled into the bundle, never a place for credentials.

| Environment | API route |
| --- | --- |
| Website development | Existing relative `/api`, proxied by Vite to port 8000 |
| Website deployment | Same-origin `/api`; optional HTTPS `VITE_API_BASE_URL` requires web CORS/reverse proxy as appropriate |
| iOS simulator | Set `VITE_API_BASE_URL` to a reachable HTTPS backend/tunnel |
| Physical iPhone | Set the same variable to a reachable HTTPS backend/tunnel; the phone's localhost is not the Mac |
| Production iOS | A stable authenticated-as-needed HTTPS backend with a valid certificate; deployment/security review remains required |

From `api/`, start the normal backend. To test from a device, one option is a local
HTTPS tunnel to port 8000 (`cloudflared tunnel --url http://localhost:8000`). This
exposes the guest API to anyone who knows the URL; use a controlled temporary test
environment and close the tunnel afterward. Do not share the Gemini key.

Create ignored `web/.env.ios.local` with the following shape, replacing the example
with the actual reachable origin (no `/api` suffix):

```dotenv
VITE_API_BASE_URL=https://your-backend.example
```

That example is not a working backend. The iOS build rejects missing, HTTP,
credential-bearing and loopback origins. Do not set `server.url` or bundle a remote
website: packaged React assets load locally. Capacitor's built-in HTTP bridge
patches fetch only inside native and supports the existing multipart WAV requests;
no P1 CORS changes or new audio/network plugin were added. See
[Capacitor HTTP](https://capacitorjs.com/docs/apis/http). Native in-flight uploads
may finish server-side after JS cancellation; aborted/stale replies cannot alert.
Never put a secret in any `VITE_` variable, since these are public bundle contents.

## Build and launch

```sh
cd web
npm ci
npm run ios:sync
npm run ios:open
```

`ios:sync` type-checks, builds with Vite's `ios` mode and copies `dist/` into
`ios/App/App/public`. Build assets/config are ignored; rerun after cloning or any
frontend/backend-origin changes. `ios:open` opens `ios/App/App.xcodeproj`.
Choose the App scheme and an iPhone simulator, then Run. On a physical iPhone,
choose your own signing team, review the bundle ID, connect/trust the phone and
use Xcode's normal development workflow. No signing credentials belong in Git. Native bridge logging is disabled so audio
payloads are not emitted by development bridge logs.

`npm run build` remains the independent website build; both builds use `dist/`,
so rerun `ios:sync` before building Xcode after a website build. Do not distribute
validation bundles built with an example URL. No native release is validated yet.

## Microphone, storage and foreground scope

NSMicrophoneUsageDescription explains teaching/listening. Both actions retain the
existing user-triggered getUserMedia → AudioWorklet → WAV pipeline. Startup is OFF;
Teach can request permission independently. Denial directs native users to iPhone
Settings. No native AAC/M4A recorder or format substitution is used. Examples and
detection remain exactly 48,000 mono PCM16 samples at 16 kHz; room recording is
160,000 samples. Review/playback/re-record/acceptance and Teach/Listen exclusivity
use the same implementation as the website.

The foreground App-level listener survives page navigation and uses existing
filtering, enabled settings, visual alerts and local History. Guest metadata stays
in WKWebView localStorage under the stable app origin, separate from Safari/web
storage; reinstalling/clearing app data can remove it. Taught models live on the
selected backend; reconnecting to a different backend does not migrate them.
No login or persistent audio storage was added. No native notification permission
is requested: alerts are in-app visual overlays, not background push notifications.

This release intentionally supports foreground listening only. Scene backgrounding
and audio-session interruption stop WebView capture and notify JS; returning does
not restart it. Permission dialogs are not treated as background transitions.
Late grants are released, including when a native interruption happens while
permission is pending. Browser context/track interruption remains handled.

**Locked-screen/background detection is not implemented or verified.** JavaScript
and WebView networking are not an indefinite background service. A future native
Swift audio service would need a supported recording AVAudioSession, appropriate
background entitlement/mode, native windowing/upload lifecycle and interruption
handling, user-visible controls/notifications, and physical-device testing. Merely
adding UIBackgroundModes is insufficient. This project enables no background audio
mode or silent-audio workaround. See Apple's
[audio recording category](https://developer.apple.com/documentation/avfaudio/avaudiosession/category-swift.struct/record).

## Required physical-iPhone acceptance checks

1. Fresh install/launch: OFF, no microphone or notification prompt. Navigate pages;
   no microphone stream. Start Listen, allow access, check one stream and real
   requests to FastAPI. Health alone does not verify Gemini authentication.
2. Deny once, retry, enable in Settings, and retry again. Verify the explanation
   matches the actual failure. Teach before Listen and repeat independently.
3. Record 3 × 3 s examples and 10 s room noise. Review/play/re-record and accept
   individually; inspect uploaded WAV headers/rate/channels/sample counts. Save
   with a real backend and check self-check/custom recognition. Failed saves keep
   clips for retry. There is no separate check-only API endpoint.
4. Start Listen and navigate Home/Your Sounds/History/Teach/Login and back. A safe
   target detection off Listen must show the same visual alert and one local
   History entry. Check disabled categories and re-enabling. Teach capture/preview
   must not feed detection; resume only if previously enabled. Stop releases tracks;
   late replies cannot alert. Relaunch returns OFF.
5. Background, lock, receive an audio interruption, and foreground: capture must
   stop and require explicit restart. Check late permission grants too. Do not
   claim background coverage if the OS/device behavior has not been observed.
6. Check small/large iPhones, notches/Dynamic Island, portrait, home indicator,
   keyboard and scrolling, larger system text/pinch zoom, VoiceOver controls/focus,
   reduced motion, dark/light theme and contrast. Existing desktop layout must
   stay unchanged. Native-only safe-area rules must not apply to website desktop.
7. Verify persistence after force-close/relaunch with listening OFF, offline/backend
   failure recovery, and real near/far/mixed sound trials. Record false alerts and
   missed events; do not infer whole-house reliability from synthetic audio.

Automated checks cover WAV encoding, lifecycle cleanup (including native-inactive
and pending grants), API origin validation, shared listening/retries and existing
frontend behavior. `web/tests/browser-global-listening.mjs` exercises generated
browser audio, not physical microphone/WKWebView. Xcode compilation and all native
acceptance checks above remain outstanding until full Xcode/device access exists.
