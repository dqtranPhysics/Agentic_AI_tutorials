#!/usr/bin/env python3
"""Read-only summary of DICOM-RT files with a PHI check.

Usage:
    python inspect_dicom.py <file-or-folder> [--phi-only] [--json] [--show-phi]

PHI values are masked unless --show-phi is passed (never use that in a shared log).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import pydicom
except ImportError:  # pragma: no cover
    sys.exit("pydicom is not installed. Run: uv sync --extra dicom")

PHI_TAGS = [
    "PatientName", "PatientID", "PatientBirthDate", "PatientSex", "PatientAge",
    "PatientAddress", "PatientTelephoneNumbers", "OtherPatientIDs",
    "InstitutionName", "InstitutionAddress", "ReferringPhysicianName",
    "PhysiciansOfRecord", "OperatorsName", "AccessionNumber",
    "StudyDate", "SeriesDate", "AcquisitionDate", "ContentDate", "StudyID",
]


def mask(value: str) -> str:
    return " ".join(w[0] + "*" * (len(w) - 1) if w else w for w in str(value).split())


def phi_report(ds, show: bool) -> dict:
    found = {}
    for tag in PHI_TAGS:
        val = getattr(ds, tag, None)
        if val not in (None, "", []):
            found[tag] = str(val) if show else mask(val)
    return found


def summarize(ds) -> dict:
    mod = getattr(ds, "Modality", "?")
    out: dict = {"modality": mod, "sop_class": str(getattr(ds, "SOPClassUID", ""))}
    if mod in ("CT", "MR", "PT"):
        out.update(
            series=str(getattr(ds, "SeriesDescription", "")),
            pixel_spacing_mm=[float(x) for x in getattr(ds, "PixelSpacing", [])],
            slice_thickness_mm=float(getattr(ds, "SliceThickness", 0) or 0),
        )
    elif mod == "RTPLAN":
        beams = []
        mu = {}
        for fg in getattr(ds, "FractionGroupSequence", []):
            out["fractions"] = int(getattr(fg, "NumberOfFractionsPlanned", 0) or 0)
            for rb in getattr(fg, "ReferencedBeamSequence", []):
                mu[int(rb.ReferencedBeamNumber)] = float(getattr(rb, "BeamMeterset", 0) or 0)
        seq = getattr(ds, "BeamSequence", None) or getattr(ds, "IonBeamSequence", [])
        for b in seq:
            cps = getattr(b, "ControlPointSequence", None) or getattr(b, "IonControlPointSequence", [])
            energy = getattr(cps[0], "NominalBeamEnergy", None) if cps else None
            beams.append({
                "number": int(b.BeamNumber),
                "name": str(getattr(b, "BeamName", "")),
                "radiation": str(getattr(b, "RadiationType", "")),
                "energy": float(energy) if energy is not None else None,
                "MU": mu.get(int(b.BeamNumber)),
            })
        out.update(plan_label=str(getattr(ds, "RTPlanLabel", "")), beams=beams)
    elif mod == "RTDOSE":
        scaling = float(getattr(ds, "DoseGridScaling", 1.0))
        offsets = [float(x) for x in getattr(ds, "GridFrameOffsetVector", [])]
        dz = sorted({round(b - a, 4) for a, b in zip(offsets, offsets[1:])})
        info = {
            "rows_cols_frames": [int(ds.Rows), int(ds.Columns), int(getattr(ds, "NumberOfFrames", 1))],
            "pixel_spacing_mm": [float(x) for x in ds.PixelSpacing],
            "slice_spacings_mm": dz,
            "dose_grid_scaling": scaling,
            "summation_type": str(getattr(ds, "DoseSummationType", "")),
            "units": str(getattr(ds, "DoseUnits", "")),
        }
        try:
            info["max_dose_Gy"] = float(ds.pixel_array.max() * scaling)
        except Exception as exc:  # pixel data may need extra handlers
            info["max_dose_Gy"] = f"unavailable ({exc.__class__.__name__})"
        out.update(info)
    elif mod == "RTSTRUCT":
        out["rois"] = [
            {"number": int(r.ROINumber), "name": str(r.ROIName)}
            for r in getattr(ds, "StructureSetROISequence", [])
        ]
    out["frame_of_reference"] = str(getattr(ds, "FrameOfReferenceUID", ""))
    return out


def iter_files(path: Path):
    if path.is_file():
        yield path
    else:
        for p in sorted(path.rglob("*")):
            if p.is_file():
                yield p


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", type=Path)
    ap.add_argument("--phi-only", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--show-phi", action="store_true", help="print unmasked PHI (local use only)")
    args = ap.parse_args()

    results = []
    for f in iter_files(args.path):
        try:
            ds = pydicom.dcmread(f, stop_before_pixels=False, force=False)
        except Exception:
            continue  # not DICOM
        rec = {"file": str(f), "phi": phi_report(ds, args.show_phi)}
        if not args.phi_only:
            rec["summary"] = summarize(ds)
        results.append(rec)

    n_phi = sum(1 for r in results if r["phi"])
    if args.json:
        print(json.dumps({"files": results, "files_with_phi": n_phi}, indent=2))
        return
    for r in results:
        print(f"== {r['file']}")
        if "summary" in r:
            for k, v in r["summary"].items():
                print(f"   {k}: {v}")
        print(f"   PHI tags populated: {sorted(r['phi']) or 'none'}")
    print(f"\n{len(results)} DICOM file(s); {n_phi} contain populated PHI tags.")
    if n_phi:
        print("!! Do not copy these to HPC or share them until de-identified per your IRB/DUA.")


if __name__ == "__main__":
    main()
