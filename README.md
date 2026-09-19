# Nebula Wayside

**An explainable, operator-focused train condition-monitoring platform for NebulaX 2026 Problem Statement 3.**

Nebula Wayside converts raw rail-vehicle sensor data into validated predictions, operational decisions, and submission-ready outputs across all four competition subsystems:

- Door abnormal-resistance detection
- Air-conditioning refrigerant-leak localisation
- Rail-corrugation classification
- Structural fatigue-damage estimation

The project combines physics-informed modelling, leakage-safe validation, explainable visualisations, fleet-level incident management, live Singapore transport context, and strict competition-schema validation in one Streamlit application.

---

## Contents

- [Challenge](#challenge)
- [What was built](#what-was-built)
- [Subsystems and results](#subsystems-and-results)
- [Application capabilities](#application-capabilities)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [Using the application](#using-the-application)
- [Command-line inference](#command-line-inference)
- [Competition dataset](#competition-dataset)
- [Building the submission](#building-the-submission)
- [Validation methodology](#validation-methodology)
- [Live data integrations](#live-data-integrations)
- [Learning loop](#learning-loop)
- [Deployment](#deployment)
- [Testing](#testing)
- [Repository structure](#repository-structure)
- [Known limitations](#known-limitations)
- [Submission status](#submission-status)
- [Documentation](#documentation)

---

## Challenge

This project addresses **Problem Statement 3: Train Condition Monitoring** from the LTA NebulaX 2026 Hackathon.

Rail vehicles generate large volumes of sensor data during normal operation. The challenge is to turn those signals into useful condition-monitoring decisions without relying solely on manual inspection or fixed thresholds.

The official challenge defines four independent tasks:

| Subsystem | Task | Input signals | Official metric |
|---|---|---|---|
| Door | Detect door cycles and classify normal versus abnormal resistance | Motor current, voltage, back-EMF, commands, switches and leaf position | IoU-weighted F1 |
| ACV | Rank cars by likelihood of a refrigerant leak | Cabin temperature, ambient temperature and operating-mode telemetry | Linear rank-decay score |
| Rail corrugation | Classify each recording as Normal, Side I or Side II | Multi-channel axle-box vibration and shock | Macro F1 |
| Structural health monitoring | Estimate cumulative fatigue damage | Dynamic stress time series | `max(0, 1 − MAPE)` |

Each subsystem contributes 25% of the competition’s Overall Score. Attempting all four therefore maximises possible coverage.

The original challenge package is available from the [NebulaX Hackathon Problem Statement repository](https://github.com/aochinwen/NebulaX-Hackathon-ProblemStatement).

---

## What was built

Nebula Wayside contains:

- Four working condition-monitoring pipelines
- A single Streamlit application for non-technical users
- Automatic file-type and subsystem detection
- Explainable, subsystem-specific visualisations
- Operator and Engineer views
- Actionable recommendations with urgency and ownership
- A fleet work queue with acknowledge, shelve and close workflows
- A network map with weather and optional LTA live-data integrations
- Official competition metrics and submission schemas
- Leakage-safe cross-validation and model cards
- A shared inference path for the UI, CLI and submission builder
- Automatic generation of all four prediction CSVs
- Automatic creation and validation of `predictions.zip`
- Submission-folder packaging
- Docker and Google Cloud Run deployment support
- A gated learning loop based on confirmed operator outcomes

The interface is designed around a simple operational question:

> What is wrong, how confident are we, and what should the operator do next?

---

## Subsystems and results

The following results are cross-validated estimates on the supplied training data. They are not held-out leaderboard results.

| Subsystem | Method | Validation strategy | Score |
|---|---|---|---:|
| Door | Gap-based cycle segmentation and a class-balanced random forest using per-cycle electrical and motion features | Five contiguous time blocks | **0.9909 ± 0.0182** IoU-weighted F1 |
| ACV | Fraction of cooling readings where each car is more than 2 °C hotter than its peers, with mean excess as a tie-break | Leave-one-case-out | **1.0000 ± 0.0000** rank-decay score |
| Rail corrugation | Per-side vibration, shock, spectral and measured-speed features with a balanced random forest | Stratified grouped CV and repeated model selection | **0.8290 ± 0.0594** macro F1 |
| Structural health | ASTM E1049 rainflow counting and Miner’s rule with fitted S–N constants | Five-fold CV by file, fitting constants inside each fold | **0.9729 ± 0.0067** MAPE-derived score |

### Door

The Door pipeline:

1. Parses the competition’s non-standard timestamps.
2. Finds cycle boundaries from gaps in the sensor stream.
3. Extracts 27 features describing duration, motor load, electrical behaviour, movement and switch activity.
4. Classifies each cycle as:
   - `Normal`
   - `Abnormal resistance`

The training data contains 110 cycles, including 30 abnormal cycles. Within-cycle samples are approximately 0.02 seconds apart, while cycles are separated by at least 10.215 seconds. This gives a clear segmentation boundary and exact cycle endpoints.

Important features include sustained motor current, integrated current, current-to-voltage ratio and current-to-back-EMF ratio.

### Air conditioning

The ACV pipeline ranks all eight cars from most to least likely to have a refrigerant leak.

It uses peer comparison rather than absolute temperature thresholds:

1. Identify valid cooling periods.
2. Compare each car’s cabin temperature against the median of the other cars.
3. Measure the fraction of readings where the car is more than 2 °C hotter than its peers.
4. Use mean temperature excess as a tie-break.

The parser normalises inconsistent parameter names, scrambled column order, varying workbook layouts and car identifiers across the supplied Excel files.

### Rail corrugation

The Rail pipeline classifies each one-second recording as:

- `Normal`
- `Side I`
- `Side II`

It uses:

- Per-side vibration and shock statistics
- Spectral energy bands
- Axle-box layout information
- Speed estimated from the 90-tooth pulse and 0.85 m wheel diameter
- Class-balanced random forests
- Side-swap augmentation inside training folds only

The dataset is strongly imbalanced, so macro F1—not accuracy—is used for selection and reporting.

The reported nested estimate of the full model-search process is approximately **0.8034**, providing a more conservative estimate than the selected model’s original-fold score.

### Structural health monitoring

The SHM pipeline estimates cumulative fatigue damage from raw stress histories.

It follows the physical label-generation process described by the official information kit:

1. Count stress cycles using ASTM E1049 rainflow counting.
2. Apply Miner’s linear cumulative-damage rule.
3. Fit the S–N curve constants in log space.
4. Predict cumulative damage for each file.

The fitted S–N exponent is approximately **5.03**, consistent across folds and close to the standard exponent used for welded steel structures.

This physics-informed method substantially outperforms generic regression on summary statistics.

---

## Application capabilities

### Dashboard

The dashboard provides:

- A one-line fleet verdict
- Quick-drop upload for supported competition files
- Automatic subsystem routing
- Priority actions and recommended owners
- Acknowledged, shelved and closed work items
- Fleet status indicators
- Health trends
- Network-map context
- Live weather
- Recent events and alarms
- Dataset selection and management

### Subsystem pages

Each subsystem has a dedicated analysis page.

#### Door

- Detected-cycle timeline
- Normal versus abnormal verdicts
- Sustained-current visualisation
- Per-cycle inspection
- Downloadable prediction CSV

#### Air conditioning

- All-car fault ranking
- Car-level temperature-excess bars
- Cooling-period comparison
- Train schematic coloured by fault likelihood
- Downloadable prediction CSV

#### Rail corrugation

- Normal, Side I or Side II verdict
- Axle-box vibration-energy grid
- Per-side evidence
- Wavelength-domain spectrum
- Class probabilities
- Downloadable prediction CSV

#### Structural health

- Damage estimate per file
- End-of-life reference at `D = 1`
- Rainflow-cycle profile
- Damage-contribution profile
- Stress envelope
- Remaining-life projection
- Downloadable prediction CSV

### Fleet view

The Fleet view combines condition-monitoring events with operational context:

- Date and time filtering
- Line, subsystem and state filtering
- Network-map event clusters
- Train health index
- Event timeline and table
- CSV export
- NEA weather
- Optional LTA service alerts and platform crowding
- Public SGMRT updates

### Parameter monitor

A label-free analysis screen for unfamiliar datasets:

- Peer comparison across similar units
- Robust single-series drift detection
- Guidance for promoting a monitored parameter into a full subsystem

### Evidence pages

The application includes dedicated pages for:

- Cross-validation results
- Fold-level scores and variation
- Baselines
- In-sample versus out-of-fold comparisons
- Model-search experiments
- Methodology and architecture
- Competition submission generation

---

## Architecture

```text
Uploaded files or bundled test data
                │
                ▼
       Subsystem registry
        core/registry.py
                │
                ▼
  subsystems/<key>/predict.py
       predict() and analyze()
                │
      ┌─────────┴─────────┐
      ▼                   ▼
Streamlit pages     CLI / submission build
      │                   │
      └─────────┬─────────┘
                ▼
 Official schema validation
      core/submission.py
                │
                ▼
 Prediction CSVs / predictions.zip
```

Key design decisions:

- The app contains no duplicated modelling logic.
- The UI, CLI and submission builder call the same subsystem `predict()` and `analyze()` functions.
- Every downloadable result passes the official schema validator.
- Models and validation metadata live beside each subsystem.
- Adding another subsystem requires a package plus one registry entry.
- The application still starts when the 7.6 GB competition dataset is absent.
- Uploaded files can be analysed without cloning the original dataset.

---

## Quick start

### Requirements

- Python 3.12 or newer
- Git
- Approximately 8 GB of free space if cloning the complete competition dataset

No GPU is required.

### 1. Clone the application

```bash
git clone https://github.com/mantaikosauce/mentaikolychee-train-monitoring.git
cd mentaikolychee-train-monitoring
```

### 2. Create an environment

#### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

#### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Start the application

```bash
python -m streamlit run app/streamlit_app.py
```

Open [http://localhost:8501](http://localhost:8501).

### Windows one-command setup

A setup script can create the environment, install dependencies, clone the competition dataset, run the test suite and build the predictions:

```powershell
powershell -ExecutionPolicy Bypass -File TAKEOVER\setup.ps1
```

To install the application without downloading the full dataset:

```powershell
powershell -ExecutionPolicy Bypass -File TAKEOVER\setup.ps1 -SkipDataset
```

---

## Using the application

1. Open the Dashboard.
2. Drag a Door CSV, Rail CSV, SHM CSV or ACV XLSX file into the uploader.
3. Let the application identify the subsystem.
4. Review the verdict and recommended action.
5. Open the corresponding subsystem page for detailed evidence.
6. Download the validated prediction CSV.
7. Use the Submission page to generate `predictions.zip` when all test inputs are available.

The application can operate in upload-only mode. The cloned competition dataset is needed only for bundled test runs and automatic full-submission generation.

---

## Command-line inference

The project includes a CLI using the same inference and validation path as the application.

### Door

```bash
python predict.py \
  --subsystem door \
  --input path/to/Test.csv \
  --output door_predictions.csv
```

### ACV

```bash
python predict.py \
  --subsystem acv \
  --input path/to/acv_test_case.xlsx \
  --output acv_predictions.csv
```

### Rail

```bash
python predict.py \
  --subsystem rail \
  --input path/to/rail/files \
  --output rail_predictions.csv
```

### Structural health

```bash
python predict.py \
  --subsystem shm \
  --input path/to/stress/files \
  --output shm_predictions.csv
```

### All subsystems using bundled test data

```bash
python predict.py --subsystem all --output predictions/
```

The `--input` option accepts one or more files or a directory.

---

## Competition dataset

The original competition repository is intentionally not committed to this project because it is approximately 7.5 GB.

Clone it into `repo/`:

```bash
git clone --depth 1 \
  https://github.com/aochinwen/NebulaX-Hackathon-ProblemStatement.git \
  repo
```

The expected layout is:

```text
repo/
└── PS3/
    ├── 01_Problem_Statement_3_Specifications.md
    ├── 02_Datasets/
    │   ├── Door/
    │   ├── ACV/
    │   ├── Rail_Corrugation/
    │   └── SHM/
    ├── 03_References/
    └── 04_Example_Submission/
```

The application expects datasets below:

```text
repo/PS3/02_Datasets/
```

Do not commit the raw competition dataset.

---

## Building the submission

### Generate all predictions

```bash
python -m scripts.build_predictions
```

This command:

1. Loads all available subsystem models.
2. Runs them over the bundled test inputs.
3. Validates every prediction table.
4. Writes the individual CSV files.
5. Creates `predictions/predictions.zip`.
6. Refreshes the dashboard analysis cache.

Expected files inside `predictions.zip`:

```text
door_predictions.csv
acv_predictions.csv
rail_predictions.csv
shm_predictions.csv
```

All files are written at the ZIP’s top level, as required by the competition specification.

### Package the complete team submission

```bash
python -m scripts.package_submission --team "Your Registered Team Name"
```

Optionally include the demo video:

```bash
python -m scripts.package_submission \
  --team "Your Registered Team Name" \
  --video path/to/demo_video.mp4
```

The resulting structure is:

```text
dist/
└── Your Registered Team Name/
    ├── demo_video.mp4
    ├── predictions.zip
    ├── app/
    └── Optional_Items/
        ├── write_up.md
        ├── DESIGN.md
        ├── PROJECT-STATE.md
        ├── Door/
        ├── ACV/
        ├── Rail Corrugation/
        └── SHM/
```

The packaging script excludes raw datasets, environments, caches and Git metadata.

---

## Official output schemas

| File | Required columns |
|---|---|
| `door_predictions.csv` | `start_time`, `end_time`, `prediction` |
| `acv_predictions.csv` | `file_id`, `ranked_cars` |
| `rail_predictions.csv` | `file_id`, `prediction` |
| `shm_predictions.csv` | `file_id`, `prediction` |

Additional validation includes:

- Exact column order
- No missing values
- Valid label spelling
- Native Door timestamp format
- Positive finite SHM values
- Two-digit ACV car identifiers
- No duplicate car rankings
- File IDs containing their extensions
- Complete and non-duplicated expected file sets
- No unexpected files
- No partial ZIP creation after validation failure

---

## Validation methodology

The project follows four principles:

1. **Use the official metric.**  
   All four scoring formulas are implemented in `scoring/metrics.py`.

2. **Prevent leakage.**  
   Door uses time blocks, ACV holds out entire cases, Rail groups by recording, and SHM fits physical constants inside every fold.

3. **Report uncertainty.**  
   Model cards include fold-level scores, means, standard deviations, baselines and caveats.

4. **Keep model selection honest.**  
   Rail experiments use repeated grouped validation and report a nested estimate of the model-search process.

Model metadata is stored in:

```text
subsystems/<key>/artifacts/config.json
```

Supporting benchmarks and experiment decisions are stored alongside each model.

---

## Live data integrations

### NEA weather

Weather information is loaded from Singapore’s public data services and does not require an API key.

The interface continues to work if the feed is unavailable.

### LTA DataMall

An optional LTA DataMall AccountKey enables additional operational context, including service alerts and platform crowding where available.

Users enter the key for the current session on the Fleet page. Keys are not committed to the repository.

Register through the [LTA DataMall portal](https://datamall.lta.gov.sg/).

### SGMRT

The Fleet view can link to the public SGMRT channel for additional service information.

Live integrations enrich the operational picture but are not required for model inference.

---

## Learning loop

Closed work-queue events can record:

- Confirmed fault
- No fault found
- Inconclusive outcome

Uploaded evidence is retained locally under `data/uploads/`, and retraining attempts are logged.

Run a dry-run evaluation with:

```bash
python -m scripts.retrain --dry-run
```

Door and Rail models may be retrained when sufficient confirmed outcomes exist. Promotion is gated by pre-registered performance conditions.

SHM and ACV are not automatically retrained:

- SHM is governed by a fitted physical fatigue model.
- ACV uses a fixed peer-comparison rule.

Feature-distribution drift is monitored against the saved training statistics and surfaced on subsystem and Validation pages.

---

## Deployment

### Docker

Build and run locally:

```bash
docker build -t nebula-wayside .
docker run -p 8080:8080 nebula-wayside
```

Open [http://localhost:8080](http://localhost:8080).

### Google Cloud Run

Prerequisites:

- A Google Cloud project with billing enabled
- The `gcloud` CLI
- Cloud Run, Cloud Build and Artifact Registry enabled

Deploy from the project root:

```bash
gcloud run deploy nebula-wayside \
  --source . \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 900
```

The container:

- Uses Python 3.12
- Binds Streamlit to `0.0.0.0`
- Uses the Cloud Run-provided port
- Supports uploads up to 400 MB
- Does not require the original 7.5 GB dataset
- Can scale to zero when idle

See [`deploy/CLOUD_RUN.md`](deploy/CLOUD_RUN.md) for operational notes.

### Streamlit Community Cloud

Configure:

- Repository: this repository
- Branch: `main`
- Main file: `app/streamlit_app.py`
- Python: 3.12

The upload-based workflow works without cloning the competition dataset.

---

## Testing

Run the main test suite:

```bash
python -m pytest tests -q
```

The tests cover:

- Official scoring metrics
- Published metric examples
- Submission schemas
- CLI behaviour
- Prediction packaging
- Page rendering
- User interactions
- Insight generation
- Learning-loop behaviour
- Ported subsystem integrations

Subsystem-specific checks are also available:

```bash
python -m subsystems.door.tests.smoke_test
python -m subsystems.shm.tests.smoke_test
```

Model or application changes should not be promoted until the relevant tests and validation experiments pass.

---

## Repository structure

```text
.
├── app/                         Streamlit UI and visual components
│   ├── streamlit_app.py
│   ├── charts.py
│   ├── components.py
│   ├── insight.py
│   ├── livemap.py
│   ├── lta_live.py
│   ├── network.py
│   ├── schematics.py
│   └── theme.py
├── core/                        Shared application infrastructure
│   ├── cache.py
│   ├── decisions.py
│   ├── drift.py
│   ├── events.py
│   ├── quickdrop.py
│   ├── registry.py
│   └── submission.py
├── subsystems/
│   ├── door/
│   ├── acv/
│   ├── rail/
│   ├── shm/
│   └── generic/
├── scoring/
│   └── metrics.py               Official metric implementations
├── scripts/
│   ├── build_predictions.py
│   ├── package_submission.py
│   ├── model_search.py
│   ├── retrain.py
│   ├── feature_stats.py
│   └── write_up.py
├── tests/                        Application and integration tests
├── predictions/                  Validated competition outputs
├── data/stations/                Bundled station-map data
├── design-system/                Design tokens and component definitions
├── deploy/                       Cloud Run deployment resources
├── TAKEOVER/                     Fresh-machine and handover tools
├── predict.py                    Command-line inference
├── Dockerfile
├── requirements.txt
├── environment.yml
├── DESIGN.md
├── PROJECT-STATE.md
├── START_HERE.md
└── WRITEUP.md
```

---

## Known limitations

- Cross-validation results are estimates from the supplied training data, not official held-out leaderboard scores.
- Door validation is based on one door and one recording; its score may overstate generalisation to other hardware.
- ACV has only six labelled cases, and some ranking margins are narrow.
- Rail Side I is the rarest and most difficult class.
- SHM load conditions are not recoverable as explicit per-file metadata.
- Large Rail batches can require substantial memory.
- Live feeds are external dependencies and may be unavailable or rate-limited.
- The original competition dataset is not distributed with this repository.
- Operator outcomes are stored locally unless a persistent external data store is added.
- The interface supports maintenance decisions but does not replace engineering inspection or safety procedures.

---

## Submission status

| Deliverable | Status |
|---|---|
| Door model | Complete |
| ACV model | Complete |
| Rail model | Complete |
| SHM model | Complete |
| Unified application | Complete |
| Prediction CSVs | Complete |
| Schema-validated `predictions.zip` | Complete |
| Submission packager | Complete |
| Technical write-up | Complete |
| Docker deployment | Complete |
| Cloud Run configuration | Complete |
| Demo video | Still to be recorded |
| Team-owned Cloud Run deployment | Still to be completed |

Recommended demo flow:

1. Open the Dashboard.
2. Upload a competition-format file.
3. Show automatic subsystem detection.
4. Review the verdict and action.
5. Open the detailed subsystem evidence.
6. Download the prediction.
7. Build `predictions.zip` from the Submission page.

The competition demo must not exceed three minutes.

---

## Documentation

| Document | Purpose |
|---|---|
| [`START_HERE.md`](START_HERE.md) | Fastest route from a new machine to a working application |
| [`PROJECT-STATE.md`](PROJECT-STATE.md) | Verified data facts, scores and technical decisions |
| [`DESIGN.md`](DESIGN.md) | Interface principles, operational design and sources |
| [`WRITEUP.md`](WRITEUP.md) | Competition methodology and results |
| [`app/README.md`](app/README.md) | Application pages and architecture |
| [`deploy/CLOUD_RUN.md`](deploy/CLOUD_RUN.md) | Deployment guide |
| [`TAKEOVER/README.md`](TAKEOVER/README.md) | Project handover and recovery guide |

---

## Acknowledgements

Built for the **LTA NebulaX 2026 Hackathon, Problem Statement 3: Train Condition Monitoring**.

The project uses the official challenge specifications, subsystem information kits, datasets and submission schemas supplied through the NebulaX Hackathon repository.
