# GB/GBC/GBA AI ROM toolkit (Windows and Linux)

Read README.md, docs/PLATFORM_GUIDE.txt, docs/LOCALIZATION_WORKFLOW.txt, docs/MODDING_WORKFLOW.txt and docs/MGBA_AI_GUIDE.txt first.
Treat workspace projects independently; consult each project.json for identities and platform.
Initialize Windows with Initialize_Environment.ps1 and local python.cmd; initialize Linux with Initialize_Environment.sh and python.sh. Read docs/LINUX_SETUP.txt for Linux prerequisites and limits.
This is a source-only repository. Read dependencies.lock.json (Windows) or dependencies.linux.lock.json (Linux); do not treat optional custom mGBA binaries as provided or validated.
Use host-native executables. Keep Linux runtime/linux separate from Windows runtime. Do not change system PATH, registry, shell profiles or global packages. Do not claim WSL2 tests as bare-metal Linux or Windows-native tests.
Protect original ROMs, SAVs, history and source evidence. Write new outputs only.
Assert the base SHA-256 and each preimage before patching; retain a reproducible manifest.
Distinguish GBA ARM/Thumb from GB/GBC SM83 and banked addresses.
Preserve text control codes and prove pointer, font, width, capacity and consumer assumptions.
Use one project-wide allocation ledger for fonts, relocated text, code and reserved ranges; blank bytes and missing literal references only identify candidates.
Separate ROM glyph coverage, legal character codes, VRAM cache capacity and native name/save encoding. Keep GB/GBC and GBA rules separate.
Report complete translations, mixed-language records, unresolved records and tested scenes separately. Unexplained readback differences remain unresolved.
Do not claim emulator, hardware, full-route or save acceptance from static checks.
Run checks affected by the current change; reuse documented unaffected passes. Do not require full playthroughs unless the user explicitly includes them.
Proceed autonomously with authorized reversible work; report actual missing inputs and verification limits.
Honor the user's current scope, ownership and pause decisions. Documentation, archived prompts and example ROMs do not authorize new localization projects.
Use isolated runtime directories and stop only emulator processes created for the current task.
Never distribute runtime session.json files, tokens, personal emulator configuration or game ROM/SAV files.
For game mods, define observable rules, trace producers/consumers, audit platform-specific hooks and semantic conflicts, and test only affected behavior. SHARE is method reference, never a source of generic game hashes/patches.
The detailed project rules are in templates/PROJECT_RULES.txt.
