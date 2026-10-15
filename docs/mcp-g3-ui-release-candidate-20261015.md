# G3/UI-aligned MCP read-only release candidate — NOT DEPLOYED

Verified date: 2026-10-15 (Saint Lucia). Owner authorized preparation and conditional live deployment only after full security review and rollback. Branch-only / no main changes remains in force.

## Exact observed live runtime
- Host v79sl, Hub, PostgreSQL, business agent, Tiquet reported healthy.
- Hub image: sha256:ac3f3262476deeba190a362a6782e02836fff2a7d701ab219a60be7f8caaba0e.
- OCI source revision: 8d82b21a4defe47a3d377a57dcd648b3c9818fea.
- Runtime server.ts SHA256: b6125ad6d2add67b564070322d057739017aa91270897d4927ebd072f3de47b2.
- Runtime server.ts Git blob: 51d887fa7cf3b722525052044716d05ed673c66e.
- GitHub c42f671 and 8d82b21 server.ts Git blobs BOTH match live. 8d82 is 11 commits ahead of c42; later changes include UI, marketing, and tests.
- Eight live Compose layers all present with user-supplied SHA256:
1. 186175ec20d10f817a9468b305fed86a6b0b4ae7cd380659e574df95ef688261 /opt/v79/hub/docker-compose.yml
2. 8aa57bba2c6955ab5affe5394ed7bec2b9b2693bc05556db3bef0420bcc04b74 /opt/v79/hub/releases/wipay-return-585f701.pinned.yml
3. fddb7d2a6934dfa65a5ce05358ca71a6769eebdff8c7def760eb070adac2b4c5 /home/firelion/.v79-g12-pinned-cutover-49318a690822/candidate-v4.yml
4. 44e177b5c5cd8138ea42139bd6cbd5d82452a2a83585db88ef4f50e74519bd34 /home/firelion/v79-g2-cutover-f7d8b9f4d648-v3/g2-disabled.yml
5. 51cb2fb1629f1900a363aed090a1066d27f1ed2b97a63372b951d85bcd07591f /home/firelion/v79-g2-cutover-f7d8b9f4d648-v3/g2-enabled.yml
6. cfac41db973d8f99b9e3675389988cef9e009d5dc9cdae39d07dc0a900eb7bda /home/firelion/v79-g3-recovery-20261014T220437Z-bp9zg67v/g3-hub-disabled.yml
7. c532df563e257d2077705d48b39f0071d5fed88fcb2e9ca2874c46cba4b125c5 /home/firelion/v79-g3-cutover-c42f671f4ccd-b7934c03f0e3-v2/generation-only-v1/enable-v79-hub.yml
8. 108845250715cfb91c8db538cfafc34e189ff938fc0a56a4cbb724e8f883f168 /home/firelion/v79-g3-ui-cutover-8d82b21a4def-v3/ui-image.yml

## Safely reconciled source branch
- Feature branch feature/mcp-owner-readonly-g3-ui-20261015 created from exact G3 UI commit 8d82b21a4defe47a3d377a57dcd648b3c9818fea, NOT outdated main.
- MCP contract module and tests ported from older dev branch; only one import and one disabled-by-default read-only route inserted into exact G3 server.ts.
- Successful GitHub Actions run https://github.com/MrFixITslu/V79hub/actions/runs/38712468231 at commit 40ca38e7dbd9737d9d09023ca237c5a83f01f19a.
- Exact restored G3 server.ts bytes match 8d82 after removing MCP-only insertion; 33/33 authorization/legacy-access tests; 17/17 G3 marketing/UI and agent approval tests; complete Hub TypeScript no-emit typecheck PASS.
- Matching V79-MCP read adapter branch: feature/live-hub-authenticated-readonly-20261015 (mocked protected reads; no live token).

## Release NO-GO constraints
1. Prove encrypted current backups, independent decryption, isolated restore, pre-change immutable image rollback and correct replay of ALL EIGHT Compose overlays in original precedence order.
2. Review actual source/config of deployed image beyond just server.ts; owner acceptance for MFA, launch, WiPay and health; no generic deploy shortcut.
3. Implement and independently review proper OAuth identity, tenant-bound agent delegation, owner MFA step-up and proof-of-consent, token issuance/revocation and key rotation. Existing platform/HUB login/owner secrets cannot substitute.
4. Verify abuse controls: rate limits, monitored audit trail, narrow egress, emergency kill switch.
5. Existing main-only approved-SHA release workflow and owner's no-main instruction BOTH remain in force; no merge or bypass workflow without separate authorization.
6. No live read of private accounts, no customer data, no writes, no external ChatGPT connection until future security and deployment gates pass.

GO only for branch engineering and read-only provenance. NO-GO for production deployment, even with passing tests.