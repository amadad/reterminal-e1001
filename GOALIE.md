# Goal

Restore the four-slot kitchen reTerminal so current Family-calendar data and valid household pages render and are served automatically.

## Acceptance criteria

- Family calendar export contains current and upcoming events and refreshes automatically every 20 minutes.
- Active manifest resolves all four source paths without “source missing” notices.
- Four slots use the stable Now / Week / Focus / Action information architecture.
- Local publisher serves four verified slot hashes and the device can pull them on wake.
- Existing launchd publisher remains the sole display publisher.

## Tasks

| Task | Status | Check |
| --- | --- | --- |
| Diagnose publisher, sources, and scheduler | complete | launchd/log/source inspection |
| Restore recurring Family calendar export | complete | exporter exit 0; launchd interval 1200s |
| Repair four active source projections | complete | four-slot preview rendered without notices |
| Verify serve and device pull path | complete with physical-readback caveat | redesigned hashes served; device asleep during discovery |
