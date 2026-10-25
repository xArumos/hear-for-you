# iOS native project

The Xcode project is generated from the existing React frontend, using Capacitor
8.5.3 and Swift Package Manager. Display name: **HearAlert** (explicit user request);
provisional bundle identifier: **dev.hearforyou.app**. Review both before distribution.
The shared website continues to use the Hear For You branding.

See [the iOS setup and testing guide](../../docs/IOS.md). Run `npm run ios:sync`
from `web/` after frontend changes. Generated `App/App/public/` and native config
are ignored; they must be regenerated before building. Do not add a remote
`server.url`: the app loads bundled assets. No signing team or credentials are set.
