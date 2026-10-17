# V79 P1 COO workboard — isolated, read-only candidate

**Status:** draft source utility; **NOT integrated into Hub, not scheduled on the server, not deployed**.

The founder is selling **Hub + Tiquet only**, while the owner-only CEO/COO team coordinates V79 operations, Sentinel protects V79-owned services once its collector is verified, and other applications progress in isolated development.

## Brainstorm and REDTEAM
Three routes were considered: immediately deploy an autonomous worker; rebuild the workforce; or add a small evidenced GitHub tracking adapter to the current approved structure. The third is selected. A GitHub PR or green CI is **not** proof of running app health, restored backups, legitimate customer access, or actual Sentinel monitoring. A private repository may be inaccessible to a given token, and incomplete API pages must not be interpreted as task closure. This utility fails closed on both.

## Use only in a trusted owner-controlled shell

Python 3, stdlib only. Script: scripts/v79-coo-readonly-workboard.py.

- Run Markdown: python3 scripts/v79-coo-readonly-workboard.py
- Run JSON: python3 scripts/v79-coo-readonly-workboard.py --format json
- Test offline: python3 -m unittest discover -s tests -p 'test_v79_coo_workboard.py' -v

It uses fixed GitHub owner/repository paths and GET operations only; it cannot create tasks, run releases, or modify GitHub. It fetches open issues/PRs through the GitHub REST API without reading issue bodies, copying uncontrolled issue titles, posting data, or accessing V79 runtime health endpoints. Its work register is bounded and hand-curated; it does not pretend to assess business risk autonomously.

For the **private** V79-Sentinel repository, an operator may supply a fine-grained restricted *read-only* GitHub credential via environment variable GITHUB_TOKEN. Never put tokens in arguments, GitHub issues, chats, logs, output files or frontend environments. Store it outside the repository and use least-privilege repository access. Without a suitable credential, Sentinel's source displays UNKNOWN_SOURCE. Exit 2 means at least one repo was incomplete/unavailable: do not treat missing issues as closed.

Output includes exact collection time and GitHub issue/PR states, while runtime_health, deployed_revision and customer security GO remain explicitly UNKNOWN. A future agent must not upgrade those labels without independent signed runtime evidence. It must not make founder approvals, trigger actions or change production state.

## Deliberately out of scope

No AI model, background scheduler, Hub route, auth token scope change, service integration, Docker run, production deployment, email, account modification or customer-facing activity. No changes to the G2/G3 supervised queue, pinned WiPay release, Tiquet sessions, billing or Sentinel collectors.

## Release gates

1. Reconcile owner-approved runtime/feature baseline before Hub UI/agent integration.
2. Review the read-only REST boundary and run tests plus operator-supervised owner-only invocation.
3. Attach redacted status results; private repo failures stay UNKNOWN.
4. Only then propose signed, role-scoped COO/CEO adapter. This draft does not enable one.

Related: V79hub #152 and #138, V79-Sentinel #15.
