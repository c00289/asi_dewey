# Plan: ingest functional-safety knowledge from the ASI onboarding transcripts

**Status:** Draft 0.1, not yet executed
**Written:** 2026-10-27
**Owner:** FuSa engineer (wheel loader)
**Source:** `Roy's Brain/ASI Onboarding - Full Transcript Dump 2026-05-12/` (nine files, v.00 to v.03.e)
**Target:** `asi_dewey` database `dewey.db` and, through it, the generated workbook

---

## 1. Goal

Move everything the three onboarding sessions (2026-10-12 to 2026-10-14) said that a
functional-safety engineer on the wheel loader needs, out of the transcript folder and into
ASI Dewey, where it is queryable, exportable, and visible to agents through the command path.

"Germane to functional safety" means, for this plan:

- standards, methods, and the QMS as they apply to safety work (IEC 61508, ASPICE, ISO 9001,
  JAUS, STPA, HARA, QM/QP/QF documents, Standards Connect rules);
- every safety mechanism and administrative control that was described (layered stopping,
  E-stop, all-stop, geofence, proximity monitor, heartbeat, AOZs, performance riders);
- how ASI verifies and validates (the V, DT/OT, test infrastructure, Jama traceability,
  release cadence, parallel test) because the safety plan's right-hand deliverables depend on it;
- the product development process and the wheel loader's place in it (PDP 2.5, phases,
  SoftBank-committed schedule, Halloween-costume philosophy);
- the platform and vehicle architecture the safety concept has to cover (VCU, sensors,
  drive-by-wire versus electro-hydraulic, Mobius server and client, languages);
- the people who own test, quality, safety, platform, and the wheel loader;
- the tools, pages, and documents where safety work products live;
- the homework the sessions assigned.

Out of scope: benefits, time cards, travel, lunches, laptop setup, personal anecdotes,
culture beyond the safety-relevant values, and anything flagged in the sessions as not public
(SoftBank's total commitment, the Walmart yard-truck customer). Those stay in the transcript
folder.

## 2. What Dewey already holds (do not duplicate)

| Entity | Rows | Already there, from the workbook |
|---|---|---|
| fact | 6 | project code, Wheel Loader product line, ASAM system description, stakeholders, work tool definitions |
| person | 9 | Rod DeMay, Darsh Patel, Jerry Miller, Femi Amokomowo, Javier Quintana, four Capgemini colleagues |
| link | 20 | QMS-adjacent SharePoint items, HWL and FSS Jira boards, WL HARA 2.1, PDP gate report, ASI Academy, Claude, GitHub, Confluence |
| qms_document | 5 | QMS page, QF-17 Safety Plan template, QM-05 FuSa Management Plan, QP-11 HARA/STPA, QP-12 Change Management |
| task | 10 | week-of-10/19 onboarding tasks with Darsh, Rod, Adolfo, Femi |
| jira_ticket | 5 | HWL-2553, 2554, 2652, 2609, 2620 |
| machine_function / use_case | 34 / 21 | wheel loader functions and use cases |
| safety_plan_row | 48 | the platform safety plan matrix |

The onboarding adds nothing to machine functions, use cases, Jira tickets, or safety plan rows.
Those entities are untouched by this plan.

## 3. Decisions to make before running (recommendation first)

1. **Glossary: new entity or facts?** Recommended: add a `glossary_term` entity
   (`term`, `meaning`, `source`) by registration, exactly as the README describes, and load the
   roughly 45 safety-relevant terms into it. Fallback: put them in `fact` with names prefixed
   `Glossary:`. The entity is cleaner, gets its own sheet in the workbook, and keeps `fact`
   readable. It is a small code change plus one test.
2. **Provenance convention.** Recommended: every row created from the transcripts ends its
   text with a line `Source: onboarding D2 1:00-1:02 (v.03.c s5)`, so anyone can go back to
   the verbatim paragraph in v.00. No schema change needed. If a `source` column is wanted
   later, the automatic column migration makes it cheap to add.
3. **People without email addresses.** The transcripts give roles and names but no emails,
   and Teams misheard several names. Recommended: create the rows anyway with `text` set to
   `name as captioned; verify spelling; email TBD`, and a task to verify against the employee
   cube. The alternative, waiting until every email is known, leaves the who's-who out of the
   tool for weeks.
4. **PDP phase 0.** The `pdp_phase` lookup is `1` to `6`; the sessions described PDP 2.5 as
   phases 0 (Evaluation) to 6. Recommended: add `"0"` to the lookup. It is a one-line change
   and the lookup is soft, so nothing breaks either way.
5. **Fact numbering.** Recommended: leave `order` 1 to 9 for the workbook-era facts and use
   themed blocks for the new ones: 10s standards and QMS, 20s safety mechanisms, 30s test and
   V&V, 40s PDP and process, 50s platform and vehicle, 60s organisation and sites. The
   workbook then reads in sections.

## 4. Mechanism

Use the existing command path, nothing new.

1. **Author one script**, `data/onboarding_2026-10.jsonl`, one command per line in the
   format the script runner already takes:
   `{"verb": "create", "args": {"entity": "fact", "data": {...}}}`.
   Put it in a new top-level `data/` folder (not git-ignored; `.jsonl` is not matched by
   `*.db` or `*.xlsx`). The script is the reviewable, diffable artefact of this ingest.
2. **Rehearse on a copy.** Copy `dewey.db` to the scratchpad, then
   `asi-dewey --db <copy> --actor claude run data/onboarding_2026-10.jsonl --stop-on-error true`.
   Check `status` counts and `list fact` on the copy. The CLI already takes `--db` and `--actor`.
3. **Back up, then run for real.** `asi-dewey dump --out backups/pre-onboarding.json`, then the
   same `run` against the real database with `--actor claude` so the audit log attributes every
   row. `load backups/pre-onboarding.json --mode replace` is the undo.
4. **Verify and export.** `status` should show the deltas in section 8. Spot-check five facts,
   three people, the tasks. `export excel` and open the workbook: the new sheet (if the
   glossary entity was added) and the themed fact blocks should read cleanly.
5. **Tests.** If the glossary entity or the `pdp_phase` lookup changed, add a schema test
   (entity registered, sheet exported and re-imported) and run the suite:
   `.venv\Scripts\python -m pytest`.
6. **Changelog.** One `Unreleased` entry: glossary entity (if added), PDP phase 0, and the
   `data/` seed script.

`create` is not idempotent. Run the script once. If it has to be re-run, restore the backup
first.

## 5. Work breakdown

| # | Step | Output | Depends on |
|---|---|---|---|
| 0 | Answer the five decisions in section 3 | decisions noted at the top of this file | owner |
| 1 | Register `glossary_term` and add `"0"` to `pdp_phase` (if decided) | `schema/definitions.py`, one test | 0 |
| 2 | Write the facts block of the script from section 6 | `data/onboarding_2026-10.jsonl` | 0 |
| 3 | Write the people, links, QMS documents, tasks, glossary blocks | same file | 0, 1 |
| 4 | Rehearse on a copy, fix validation errors and lookup warnings | clean run on the copy | 2, 3 |
| 5 | Back up, run for real, verify counts, export workbook | updated `dewey.db`, `dewey.xlsx`, `backups/` | 4 |
| 6 | Changelog entry | `CHANGELOG.md` | 5 |
| 7 | Follow-up tasks (URLs, spellings, QP numbers) worked off over the next sprints | tasks closed in Dewey | 5 |

Effort: steps 1 to 6 are one working session. Step 7 is ongoing.

## 6. Inventory: facts to create

Priority A is needed for safety work now; B is useful context; C is nice to have. Sources are
Day and recording time; the v.03 section is where the condensed text lives.

### Standards, methods, QMS (order 10 to 19)

| Order | Name | Gist | Pri | Source |
|---|---|---|---|---|
| 10 | QMS foundation standards | ISO 9001 (2026 edition), ASPICE PAM 4, IEC 61508 as the foundation of FuSa management, JAUS 3.3 | A | D3 2:12-2:18, v.03.d s6.1 |
| 11 | ASPICE maturity at ASI | Level 1 five years ago, still level 1, gaps on every team; ASPICE says what, QMS maps who | A | D3 2:38-2:40 |
| 12 | ASPICE process map | SYS.1 to SYS.5, VAL.1, SWE/HWE/MLE; base practices are "the least I'll do"; SYS.3 requires bidirectional traceability (Jama); SYS.2 uses MoSCoW | A | D3 2:37-2:50 |
| 13 | QMS document taxonomy | QM policy, QP procedures (still being written), QF forms; core procedures list incl. verification, validation, hazard and risk analysis, change and configuration management; updates posted as news on the product group SharePoint | A | D3 2:19-2:21, 2:31-2:32 |
| 14 | Corrective action request | Fields: title, description, type (OFI, preventive, corrective), source, priority, related procedure or gap; routes to process owners; resolutions published as news | A | D3 2:50-2:53 |
| 15 | Standards Connect licence rules | Personal account, ASI cannot reset it, no public sharing, no wholesale copying into requirements (rewrite), destroy copies if not renewed, licence ends with contract | A | D3 2:13-2:17 |
| 16 | Quality policy | Customer focus, compliance (ISO, ASPICE, IEC, JAUS), continuous improvement, performance metrics | B | D3 2:24-2:25 |
| 17 | Standards ASI claims to know | ISO 26262 and others, tries to follow them; fairway mower is the most functionally safe vehicle, certifiable but not certified at commercialisation | A | D2 1:48-1:50 |
| 18 | AI assurance is open | How to prove an AI-driven Mobius safe is an industry question ASI's safety people are working on; CTO: the test safety net must widen for AI-generated code | A | D2 1:49-1:50 |
| 19 | HARA and STPA are the named methods | Test director: HARAs and STPAs make the brains of the robot safe; STPA Handbook provided free from the Standards page | A | D3 1:28, 2:26 |

### Safety mechanisms and controls (order 20 to 32)

| Order | Name | Gist | Pri | Source |
|---|---|---|---|---|
| 20 | Layered stopping | Vehicle perception stop; Mobius stopping-distance region (incl. known manned vehicles); choreographer slows before intersection conflicts; "two controls, vehicle and Mobius" | A | D2 1:00-1:02, v.03.c s5 |
| 21 | E-stop pendant | Auto/manual switch plus button; in autonomous mode the button e-stops and the vehicle will not resume autonomously; switch may go away as AI autonomy is trusted | A | D1 1:15-1:17 |
| 22 | All-stop | One button shuts down a whole site; owned by C4 Systems; first demonstrated 2026-10-15 at the 40-plus-machine demo outside Austin | A | D2 2:38 |
| 23 | Geofence / drivable area | Planning impossible outside the drivable-area map; Mobius will not move a vehicle beyond it | A | D1 3:45-3:46 |
| 24 | Proximity monitor and choreographer | Proximity monitor keeps checked-in vehicles apart (runs in Mobius today, intended to move on-vehicle); vehicles report at 10 Hz; choreographer is the intersection manager | A | D1 1:21, D2 0:36, 0:59 |
| 25 | Personnel and light-vehicle tracking | C4 Systems product line; operator tablets can lock a protected region; boom gates as administrative traffic control | B | D2 2:34, 2:39 |
| 26 | Heartbeat and kill (Mobius AI concept) | Mobius keeps a heartbeat with each vehicle and can send a kill signal | B | D2 1:38-1:39 |
| 27 | Determinism as a design principle | ASI kept AI out of the control loop because deterministic behaviour is provable to regulators and customers | A | D1 1:17 |
| 28 | Vehicle versus Mobius responsibilities | Vehicle always stops for what it detects; Mobius plans around what the vehicle cannot see | A | D1 3:50, 3:56-3:57 |
| 29 | Not yet certified, so administrative controls | System "not fully automated and not functionally safe certified"; AOZs with no foot traffic, radio check-in, PPE, performance riders, people-free sites; "equipment can be replaced, as long as nobody dies" | A | D3 1:44, 1:58-2:00, D1 2:40-2:41 |
| 30 | Vehicle health via CAN | CAN-bus sniffing for faults such as overheating, used to stop the machine, even on non-drive-by-wire vehicles | B | D1 1:23 |
| 31 | Mobius Mobile is deliberately limited | No map editing, no teleoperation on the phone, so map-edge safety measures need not exist there | B | D1 1:23-1:24 |
| 32 | Mode light | Kit includes a mode light so bystanders know what the vehicle is doing | C | D1 1:26-1:28 |

### Test, verification, validation (order 35 to 44)

| Order | Name | Gist | Pri | Source |
|---|---|---|---|---|
| 35 | Test mission | Safe (occupational, operational, functional), operationally effective, suitable | A | D3 1:27-1:30, v.03.d s4.1 |
| 36 | Verification versus validation | ASPICE definitions; DT/OT preferred names; who does each; capstones | A | D3 1:37-1:40 |
| 37 | Test organisation | Director of test, test management team, Texas and Utah site teams, support tiers; robot teams own their own validation and lean to verification; validation reporting to robot chiefs is an independence concern | A | D3 1:39-1:44, 2:05-2:07 |
| 38 | Test infrastructure layers | Surrogates, bench and environmental chambers, simulation, HIL/SIL rigs, vehicle on a wall, track; goal 24-6 | B | D3 1:34-1:37 |
| 39 | Test cycle | Plan-do-check-act; strategic test plan contents; "show your work"; testers inform, do not decide; fielding recommendation | A | D3 1:45-1:49 |
| 40 | Jama holds the V | Requirements and results with bidirectional traceability; test plan, suites, cases; Jira for scheduling | A | D3 1:49-1:51 |
| 41 | Parallel test | One robot in verification, one in validation; one test plan per effort, optional second for validation | B | D3 1:46-1:47, 1:51 |
| 42 | Quarterly release cadence | Hardware, software, firmware, and test frozen per quarterly demo; customers (and SoftBank) want quarterly | A | D3 2:00-2:04 |
| 43 | Solution-as-a-service tension | Things reach customers before test; managed by administrative controls and customer selection | B | D3 1:56-2:00 |
| 44 | Three core systems | Robot with payload and sensors; HMI (Mobius plus control rooms); communications | B | D3 1:31 |

### PDP and ways of working (order 45 to 51)

| Order | Name | Gist | Pri | Source |
|---|---|---|---|---|
| 45 | PDP 2.5 | Live 2026-10-19; phases 0 Evaluation, 1-2 Incubator, 3-5 Acceleration (phase 3 = job sites), 6 Commercialisation; wheel loader is in phase 3 still closing phase 2 exit | A | D2 2:45-2:47, task 4 |
| 46 | SoftBank-committed schedule | SoftBank funds all construction machines and gets quarterly status; Austin site commercial from November 2026, automation refined through 2027 (no financial figures recorded) | B | D2 2:46-2:47, D3 2:03 |
| 47 | Design philosophy | Halloween costume first, then upgrades; expect specs to be thrown out; three days not three months; unproven safety features are covered by operational procedures meanwhile | A | D2 2:47-2:57, D1 2:40-2:41 |
| 48 | Product team roles and reporting | PM what/why, program manager when, division chief and robot chiefs how; helix (two bosses) and GM model; structure in flux | B | D2 2:42-2:43, D3 2:05-2:07 |
| 49 | Scrum at ASI | Two-week company-wide sprints; stand-up adds "how AI helped"; story points are not an AI metric; one retro action per sprint | B | D3 3:08-3:22 |
| 50 | Innovation channels | IDF open to contractors with patent credit; quarterly hackathon open to contractors; Sideways Six idea box | C | D2 1:29-1:33, D3 0:59 |
| 51 | Engineering tools at a glance | Jama, Jira, Confluence (per-space access), Rovo, GitHub, Claude/Friday/App Factory, Bridge, Zendesk glossary, SharePoint, Teams, Mobius simulators | A | v.03.d s10 |

### Platform and vehicle (order 55 to 63)

| Order | Name | Gist | Pri | Source |
|---|---|---|---|---|
| 55 | What it takes to run an AV | Mobius, comms, precise localisation, VCU, sensors (LIDAR, radar, camera, IMU), proximity monitor, vehicle control, payload control | A | D1 1:19-1:23 |
| 56 | Vehicle control interfaces | Drive-by-wire over CAN, electro-hydraulic steering and braking valves, electromechanical actuators; hydraulic splicing depends on vehicle; no pedal pushers today | A | D1 1:22-1:23, D2 1:05 |
| 57 | Languages and repositories | On-vehicle C, Mobius C#, Rust discussed; VCU market code in separate repos, Mobius plug-ins in one repo and one server | B | D1 1:23, D2 1:02-1:04 |
| 58 | Mobius architecture | One ASP.NET server per site, SignalR, WPF client migrating to Blazor; Multi-Mobius (Titan, Jade); core/common/market layers | B | D2 0:36-0:46, 2:36-2:38 |
| 59 | JAUS 3.3 messaging | Robot-to-Mobius messaging on the last free JAUS version; most engineers never touch it | B | D3 2:17-2:18 |
| 60 | Tech teams | GNC, embedded (VCU), perception, localisation and mapping, planning, mechanical and electrical, mechatronics (own validation, environmental test), desktop/tools and sims (HIL, EOL rigs, simulation) | A | D1 1:26-1:46, D3 1:41-1:43 |
| 61 | Perception stance | LIDAR obstacle detection over object recognition; radar through dust and fog; fusion picks the best sensor; negative obstacles | A | D2 1:44-1:45, D1 1:41 |
| 62 | Common stack and next compute | Same core stack from haul truck to mower; Blitz installs the base stack; NVIDIA Orin-based on-vehicle compute for AI in progress | B | D2 2:43-2:44, 1:36 |
| 63 | Site mapping | GPS breadcrumb boundary drive; drones for construction sites | C | D1 1:37-1:39 |

### Organisation, sites, culture (order 65 to 69)

| Order | Name | Gist | Pri | Source |
|---|---|---|---|---|
| 65 | Where the wheel loader sits | Construction, haulage team (ADT, water truck, wheel loader); civil and haulage merging; kits installed at Southridge TX or customer sites | A | D2 2:34, D3 1:43, D2 1:05 |
| 66 | ASI market position | OEM-agnostic retrofit plus command and control; 1000-plus machines, 25 years; versus OEM walled gardens and startups weak on C&C | B | D2 2:58-3:01 |
| 67 | Sites | Mendon (track, bay, command centre), Logan (ROC), Tremonton, Dallas-Fort Worth (track, ROC), Southridge TX (site certification in Bridge), Longmont; every customer site is also a test site | B | D3 1:44, v.03.c s8 |
| 68 | Core values and sayings | Safety first among seven values; "support the second-best decision"; "fast is always right, the fight is cheap versus good" | C | D1 2:36-2:38, D2 3:12 |
| 69 | EHS rule one and AOZ protocol | Assume every machine autonomous with no obstacle detection; never walk onto a track; AOZ entry protocol; fall protection at 4 ft; LOTO | A | D1 1:58-2:05 |

Fifty facts; 27 priority A. The `text` of each is written from the v.03 condensation, not
copied verbatim, and ends with the source line.

## 7. Inventory: other entities

### People to create (person_class / nickname / text)

All with `text` = `<name as captioned>; verify spelling; email TBD` unless noted.

| Class | Nickname | Note | Source |
|---|---|---|---|
| Director of Test | Josh | Josh Williams; T&E / V&V; prefers DT/OT; admin of AI research Confluence space | D3 1:25-1:28 |
| Test Technical Lead | Quinn | Quinn Velenga (spelling unverified); leads test management team | D3 1:39-1:40 |
| QMS and Process Lead | Jed Judd | Owns QMS and standards pages; dual role with Autonomous Services; not Jed Jones (CFO) | D3 2:09-2:11 |
| EHS Manager | Dan | Dan Smith; whole-company EHS, Titan sites, monthly safety committee | D1 1:55-1:57 |
| CTO | Brian | Surname not captioned; author of PDP; AI mandate; reviews IDFs | D2 1:11-1:17 |
| VP Product Development | Todd Rigby | Oversees product divisions and the PDP | D2 2:17, 2:31 |
| VP Robotic Technology | Jeff Ferrin | Also captioned "Faron"; PAT sits under him | D2 1:17-1:19 |
| Platform Manager | Chris Mann | Perception, GNC, mechatronics, vehicle software platform | D1 0:30, 2:52 |
| Principal Architect, Perception | Taylor Bybee | | D1 1:41 |
| Mobius Core Manager | Scott McCurdy | Co-manages Mobius core with Tony | D2 0:32-0:43 |
| Training Manager | Ben Call | Ran onboarding; former FuSa tech lead; "don't bypass the safety system when testing" | D1 0:28-0:29 |
| Scrum Master | Daniel Summit | Gave the Agile session; Logan | D3 3:01 |
| Scrum Master Tech Lead | Sam Bongwo | Fort Worth | D3 0:07 |
| Capgemini | Kumari | Kumari Manjari Rani - C; same wheel loader team; automotive validation, ISO 26262; manager Jerry Miller, mentor David Waters | D2 1:09, 2:08, 1:47 |
| Wheel Loader Team | David Waters | Kumari's mentor | D2 1:09 |

Existing rows to check, not change: Rod DeMay is "Chief Engineer" in Dewey and "robot chief
for the wheel loader" in the sessions; Jerry Miller is "Validation Manager" and the sessions
put him over wheel loader test. Both are consistent; leave them.

### Links to create

Only two URLs were spoken aloud. The rest are created by name with an empty `url` and
collected in task T10 below; `url` is not a required field.

| Class | Name | URL known | Source |
|---|---|---|---|
| tool | My Apps launcher | myapps.microsoft.com | D1 0:07, 0:55 |
| n.a. | ASI intranet (SharePoint) | autonomoussolutions.sharepoint.com | D1 0:56 |
| n.a. | Standards page (Resources > Standards) | no | D3 2:12-2:13 |
| n.a. | STPA Handbook | no | D3 2:26 |
| n.a. | ASPICE PAM 4 download | no | D3 2:14 |
| n.a. | ANSI Standards Connect | no | D3 2:15 |
| n.a. | Safety SharePoint page (hazard reporting, SDS, weather) | no | D1 2:01-2:02 |
| n.a. | Zendesk glossary | no | D1 0:58-1:01 |
| n.a. | Product group SharePoint (QMS news) | no | D3 2:21 |
| n.a. | AI research Confluence space (Claude power user guide, connectors) | no | D3 0:30 |
| n.a. | Invention disclosure form | no | D2 1:29 |
| tool | Friday (ASI AI connector) | no | D3 0:30 |
| tool | Bridge: Level 2 safety certification journey | no | D3 0:10 |

### QMS documents to create

| Order | Name | Note | Source |
|---|---|---|---|
| 3 | QM-01 Quality Manual | about 13 pages; the umbrella document; URL to collect | D3 2:19, 2:31 |

The sessions named verification, validation, configuration management, document control,
management review, internal audit, nonconformance, corrective action, contract and project
review, and design and development procedures without numbers. Do not create placeholder
rows for them; the list lives in fact 13 and task T13 resolves the numbers with Darsh.

### Tasks to create (start 2026-10-14, end open unless stated)

| # | Class | Name | Comment |
|---|---|---|---|
| T1 | review | Read QM-01 Quality Manual | bookmark and download from Resources > QMS |
| T2 | administrative | Create ANSI Standards Connect login | use an ASI office address; personal licence |
| T3 | review | Read ASPICE PAM 4, SYS.1 through VAL.1 | QMS session assignment |
| T4 | review | Read ISO 9001 (30 minutes) and locate IEC 61508 on Standards Connect | QMS session assignment |
| T5 | review | Learn the corrective action request procedure | see fact 14 |
| T6 | review | Read the STPA Handbook | QP-11 is STPA-based |
| T7 | administrative | Complete Bridge Level 1 safety training | required before any task, all roles |
| T8 | status | Confirm whether Level 2 safety certification, Southridge site certification, and the PPE assessment apply to a remote contractor | ask Darsh or Ben |
| T9 | administrative | Claude setup: Desktop via My Apps, Code CLI in VS Code, connectors (M365, file system, Atlassian/Rovo, Chrome), GitHub with name-based email, AI research Confluence access | D3 0:15-0:32 |
| T10 | administrative | Collect URLs for the eleven placeholder links | update `link` rows |
| T11 | administrative | Verify captioned name spellings against the employee cube or Teams org view | update `person` rows |
| T12 | administrative | Follow and favourite the product group SharePoint site for QMS news | alerts arrive in Teams |
| T13 | status | With Darsh: which QP numbers cover verification, validation, configuration management; where wheel loader FuSa work products live (DMS, Jama, SharePoint) | feeds the safety plan location flags |
| T14 | status | Reconcile PDP 2.5 phases 0-6 with the safety plan `pdp_phase` column | decision 4 |

### Glossary terms (if the entity is added; otherwise `Glossary:` facts)

AOZ, All-stop, E-stop, Performance (safety) rider, Proximity monitor, Choreographer,
Drivable area, Negative obstacle, HIL, SIL, Vehicle on a wall, Surrogate, Tornado, DT / OT,
T&E / V&V, VCU, JAUS, Jama, PDP, PAT, AP team, C4 Systems, QM / QP / QF, QMS, Standards
Connect, ASPICE, Tech team, Blitz team, Titan, Jade, Southridge, ROC, Mobius, Mobius Mobile,
Multi-Mobius, Mobius AI, GNC, Helix, Division chief, Robot chief, Boom gate, Bridge, Rovo,
Friday, IDF, Service ID. Meanings from v.03.e section 13; source `D1 0:58-1:02` plus the
term's own reference.

## 8. Expected result

| Entity | Before | After |
|---|---|---|
| fact | 6 | 56 |
| person | 9 | 24 |
| link | 20 | 33 |
| qms_document | 5 | 6 |
| task | 10 | 24 |
| glossary_term | (none) | about 45 |
| everything else | unchanged | unchanged |

Audit log: every new row attributed to actor `claude` with the script's timestamp.

## 9. Risks and how the plan handles them

- **Caption errors.** Names and some technical terms are as Teams heard them. Every person
  row says so and task T11 closes it. Technical terms were already corrected in v.03 where the
  likely reading was clear ("pulp chambers" to HALT chambers, "JAWS" to JAUS).
- **Confidential content.** No dollar figures, no Walmart. Fact 46 says SoftBank funds the
  construction machines and nothing more.
- **Duplicates on re-run.** `create` is not idempotent; the backup in step 4.3 is the guard.
- **Workbook drift.** The workbook is a generated view; after the run, regenerate it rather than
  editing it, or the next `import excel --mode replace` would drop the new rows.
- **Staleness.** The training manager's warning applies: "what we tell you today might be wrong
  next week." The source line on every row says when it was true.

## 10. Change log

- 2026-10-27 Draft 0.1: scope, decisions, mechanism, work breakdown, full inventory.
