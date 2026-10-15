# Marketing production panel update

An open, visible production panel now fetches current worker state every ten seconds. Completion, blockers and rendered-asset buttons appear without a manual refresh. Requests are serialized, bounded to fifteen seconds, cancelled on close or hiding the tab, and resumed when the tab becomes visible. Failed reads retry automatically; mutations are never retried by this feature.

Logo selection now displays a preview, reading progress, format/size errors, and whether the logo is merely selected or saved in the approved brand. The browser validates a readable PNG up to 1 MiB and 2048 × 2048 pixels before approval. Form edits survive background reads and delayed file decoding. Selecting another file invalidates the older read. Changes reset the facts/brand confirmation; queuing a package waits until the updated brand is approved. The editor keeps its starting revision so another session's configuration change still causes a conflict.

Packages keep the approved brand captured when they were queued. A previously rendered package without a logo remains unchanged. To use a newly uploaded logo, approve the updated brand and produce a new package. Existing exact publication approvals continue to bind their original assets and destinations.

Validation: six component interaction regressions rendered with React DOM in a simulated browser DOM, existing signed bridge/MFA tests, TypeScript, production build, and dependency audit. Real Chromium could not be installed in the development environment, so visual acceptance in the owner's browser is still required after the Hub update.

This update changes the Hub UI and adds a development-only DOM testing dependency. Marketing generation, publication flags, keys, ledgers and provider integrations are not changed by the UI code.
