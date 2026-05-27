# iOS Roadmap

iOS is not part of the 0.1 alpha. Telegram is the current alpha path; Web/PWA, API, and iOS are later surfaces over the Telegram-proven core.

The iOS app is not the MVP. Build and verify the Telegram-first learning loop before mobile-app work: parent command contracts, child delivery metadata, answer watcher feedback, bounded help/repeat/next controls, parent notifications, backup/restore, and controlled E2E smoke tests.

Recommended app shape:

- one app
- Parent Mode
- Child Mode
- pairing via QR code
- Keychain token storage
- talks to a LearnBuddy Gateway, not raw generic Hermes endpoints
- APNs push only after the gateway/auth model is stable
