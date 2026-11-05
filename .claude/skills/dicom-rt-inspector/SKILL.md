---
name: dicom-rt-inspector
description: Inspect and summarize radiotherapy DICOM files (CT, RTPLAN, RTDOSE, RTSTRUCT) and check them for patient-identifying (PHI) tags before they are shared, committed, or copied to an HPC cluster. Use when the user points at a DICOM file or folder, asks what is in a plan/dose/structure set, asks for beam/MU/dose-grid details, or is about to move clinical data off a workstation.
---

# DICOM-RT Inspector

Medical physics research constantly touches clinical DICOM. This skill gives a fast,
**read-only** summary of a DICOM-RT dataset and flags PHI before data leaves a
controlled machine.

## When to use

- "What's in this plan / dose / RTSTRUCT?"
- "How many beams / what MU / what energy?"
- "What is the dose grid resolution and scaling?"
- "Is this folder safe to copy to the cluster / share with a collaborator / commit?"

## How to run

```bash
uv run python .claude/skills/dicom-rt-inspector/scripts/inspect_dicom.py <file-or-folder> [--phi-only] [--json]
```

Requires `pydicom` (`uv sync --extra dicom`). The script never modifies files.

Output per file:

| Modality | What is summarized |
|---|---|
| CT / MR | Series description, slice count, pixel spacing, slice thickness |
| RTPLAN | Plan label, # beams, radiation type, nominal energy, MU per beam (from FractionGroupSequence), # fractions, prescription if present |
| RTDOSE | Grid size, pixel spacing, `GridFrameOffsetVector` spacing, `DoseGridScaling`, max dose (Gy), dose summation type |
| RTSTRUCT | ROI names and numbers, referenced frame of reference |

Then a **PHI report**: any of the tags listed in `PHI_TAGS` in the script that are non-empty
(PatientName, PatientID, PatientBirthDate, InstitutionName, ReferringPhysicianName,
AccessionNumber, dates, etc.).

## Rules for Claude

1. **Never print PHI values into the conversation.** The script masks values by default
   (`J*** D**`). Only report *which* tags are populated, not their contents.
2. If PHI is present and the user wants to copy data to HPC or share it, **stop and say so**.
   Recommend de-identification with the institution's approved tool (e.g. a DicomAnonymizer
   or the TPS export anonymizer) — do not improvise an anonymizer unless asked, and remind
   them that IRB/data-use agreements govern what is allowed.
3. Dose values: always multiply raw pixel data by `DoseGridScaling` and state the units (Gy).
4. If `pydicom` is not installed, tell the user the `uv sync --extra dicom` command rather
   than trying to parse DICOM by hand.

## Interpreting common gotchas

- `DoseSummationType = BEAM` means a per-beam dose file — don't compare it to a plan dose.
- A non-uniform `GridFrameOffsetVector` means slice spacing varies; resample before gamma.
- RTSTRUCT and RTDOSE must share `FrameOfReferenceUID` to be overlaid without registration.
