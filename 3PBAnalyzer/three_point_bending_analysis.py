#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Three-point bending v4, based on the supplied v2 project.

Recursive CSV or reference-workbook input; per-sample geometry; optional
fracture-strain output; independent yield selection; PNG and embedded Excel plots.
All CSV units must be N and mm. See README_CN.txt for algorithm and CLI details.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import hashlib
import math
import re
from dataclasses import dataclass, asdict, replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# -----------------------------
# Data classes
# -----------------------------

@dataclass
class SampleMeta:
    sample_id: str
    file_name: str
    length_mm: Optional[float] = None
    thickness_mm: Optional[float] = None
    span_mm: Optional[float] = None
    loading_rate_mm_min: Optional[float] = None
    linear_start_mm: Optional[float] = None
    linear_end_mm: Optional[float] = None
    relative_folder: Optional[str] = None


@dataclass
class AnalysisResult:
    sample_id: str
    file_name: str
    relative_folder: Optional[str]
    length_mm: Optional[float]
    thickness_mm: Optional[float]
    span_mm: Optional[float]
    loading_rate_mm_min: Optional[float]
    max_force_n: float
    max_force_disp_mm: float
    stiffness_n_per_mm: float
    stiffness_r2: float
    stiffness_intercept_n: float
    yield_force_n: float
    yield_disp_mm: float
    postyield_disp_mm: float
    fracture_force_n: float
    fracture_disp_mm: float
    fracture_strain_pct: Optional[float]
    work_to_fracture_n_mm: float
    notes: str


# -----------------------------
# Utilities
# -----------------------------


def safe_float(v) -> Optional[float]:
    try:
        if pd.isna(v):
            return None
        return float(v) if math.isfinite(float(v)) else None
    except Exception:
        return None



def sanitize_sheet_name(name: str) -> str:
    name = re.sub(r"[\\/*?:\[\]]", "_", str(name))
    return name[:31]



def read_csv_flexible(path: Path) -> pd.DataFrame:
    encodings = ["utf-8", "utf-8-sig", "gbk", "latin1"]
    last_err = None
    for enc in encodings:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Failed to read CSV {path}: {last_err}")



def linear_regression(x: np.ndarray, y: np.ndarray) -> Tuple[float, float, float]:
    if len(x) < 2:
        raise ValueError("Need at least 2 points for linear regression")
    coef = np.polyfit(x, y, 1)
    slope = float(coef[0])
    intercept = float(coef[1])
    y_pred = slope * x + intercept
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 if ss_tot == 0 else 1 - ss_res / ss_tot
    return slope, intercept, r2



def find_best_linear_region(x: np.ndarray, y: np.ndarray, peak_idx: int,
                            manual_start: Optional[float] = None,
                            manual_end: Optional[float] = None,
                            min_points: int = 8) -> Tuple[int, int, float, float, float]:
    """
    Select the stiffness region using the same rule as the reference analysis:
    - candidate windows contain 8 to 18 points;
    - they are pre-peak;
    - window endpoints lie within 5% to 85% of Fmax;
    - net force rise across the window is at least 25% of Fmax;
    - choose the candidate with the highest R².

    A manually supplied displacement interval overrides automatic selection.
    """
    if manual_start is not None and manual_end is not None and manual_end > manual_start:
        idx = np.where((x >= manual_start) & (x <= manual_end) & (np.arange(len(x)) <= peak_idx))[0]
        if len(idx) >= 2:
            slope, intercept, r2 = linear_regression(x[idx], y[idx])
            return int(idx[0]), int(idx[-1]), slope, intercept, r2

    peak_force = float(y[peak_idx])
    if peak_force <= 0:
        raise ValueError("Peak force must be positive for stiffness-region selection.")

    best = None
    best_r2 = -np.inf
    max_points = 18

    for n_points in range(min_points, max_points + 1):
        last_start = peak_idx - n_points + 1
        if last_start < 0:
            continue
        for i in range(0, last_start + 1):
            j = i + n_points - 1
            if y[i] < 0.05 * peak_force:
                continue
            if y[j] > 0.85 * peak_force:
                continue
            if (y[j] - y[i]) < 0.25 * peak_force:
                continue

            xx = x[i:j + 1]
            yy = y[i:j + 1]
            slope, intercept, r2 = linear_regression(xx, yy)
            if slope <= 0:
                continue
            if r2 > best_r2:
                best_r2 = r2
                best = (i, j, slope, intercept, r2)

    if best is not None:
        return best

    # Fallback for unusual curves: use a broad positive pre-peak section.
    candidates = np.where((y[:peak_idx + 1] >= 0.05 * peak_force) &
                          (y[:peak_idx + 1] <= 0.85 * peak_force))[0]
    if len(candidates) >= 2:
        i, j = int(candidates[0]), int(candidates[-1])
    else:
        i, j = 0, max(1, peak_idx)
    slope, intercept, r2 = linear_regression(x[i:j + 1], y[i:j + 1])
    return i, j, slope, intercept, r2


def compute_offset_displacement(meta: SampleMeta, offset_strain: float) -> Optional[float]:
    # Standard three-point bending outer-fiber strain relation:
    # epsilon = 6 * h * delta / L^2
    # => delta = epsilon * L^2 / (6 * h)
    # Here L should be the support span.
    if meta.span_mm is None or meta.thickness_mm is None:
        return None
    if meta.thickness_mm <= 0 or meta.span_mm <= 0:
        return None
    return offset_strain * (meta.span_mm ** 2) / (6 * meta.thickness_mm)



def find_first_intersection(x: np.ndarray, y_curve: np.ndarray, y_line: np.ndarray,
                            start_idx: int = 0) -> Optional[Tuple[float, float]]:
    diff = y_curve - y_line
    for i in range(max(start_idx, 0), len(diff) - 1):
        d1 = diff[i]
        d2 = diff[i + 1]
        if d1 == 0:
            return float(x[i]), float(y_curve[i])
        if d1 * d2 < 0 or d2 == 0:
            # Linear interpolation on the difference.
            x1, x2 = x[i], x[i + 1]
            y1, y2 = y_curve[i], y_curve[i + 1]
            dd = d2 - d1
            if dd == 0:
                t = 0.0
            else:
                t = -d1 / dd
            xi = x1 + t * (x2 - x1)
            yi = y1 + t * (y2 - y1)
            return float(xi), float(yi)
    return None



def find_fracture_point(
    x: np.ndarray,
    y: np.ndarray,
    peak_idx: int,
    min_relative_drop: float = 0.20,
    min_peak_drop: float = 0.10,
    postdrop_peak_fraction: float = 0.80,
) -> Tuple[int, float, float, str]:
    """
    Detect fracture onset after peak load.

    Fracture is defined as the point immediately BEFORE the first
    substantial post-peak load drop satisfying all of the following:

    1. Relative single-step drop >= 20% of the current force.
    2. Absolute drop >= 10% of peak force.
    3. Force after the drop <= 80% of peak force.

    If no such event is found, fall back to the point immediately
    before the largest post-peak force drop.
    """
    if peak_idx >= len(y) - 1:
        return (
            peak_idx,
            float(x[peak_idx]),
            float(y[peak_idx]),
            "Peak is last point; fracture onset set to peak.",
        )

    peak_force = float(y[peak_idx])
    if not np.isfinite(peak_force) or peak_force <= 0:
        raise ValueError("Peak force must be positive and finite for fracture detection.")

    # Search from the peak and choose the FIRST substantial loss
    # of load-carrying capacity.
    for i in range(peak_idx, len(y) - 1):
        current_force = float(y[i])
        next_force = float(y[i + 1])

        if not np.isfinite(current_force) or not np.isfinite(next_force):
            continue

        drop = current_force - next_force
        if drop <= 0 or current_force <= 0:
            continue

        relative_drop = drop / current_force
        peak_drop_fraction = drop / peak_force
        postdrop_fraction = next_force / peak_force

        if (
            relative_drop >= min_relative_drop
            and peak_drop_fraction >= min_peak_drop
            and postdrop_fraction <= postdrop_peak_fraction
        ):
            note = (
                "Fracture onset defined as the point immediately before the "
                "first substantial post-peak force drop "
                f"(relative drop={relative_drop:.1%}, "
                f"drop/peak={peak_drop_fraction:.1%}, "
                f"post-drop force/peak={postdrop_fraction:.1%})."
            )
            return i, float(x[i]), current_force, note

    # Fallback for curves without a clear abrupt fracture event.
    post = y[peak_idx:]
    drops = np.diff(post)
    if len(drops) == 0:
        return (
            peak_idx,
            float(x[peak_idx]),
            float(y[peak_idx]),
            "No post-peak points; fracture onset set to peak.",
        )

    local_idx = int(np.argmin(drops))
    global_idx = peak_idx + local_idx
    note = (
        "No post-peak drop met the fracture-onset thresholds; "
        "fallback used the point immediately before the largest post-peak force drop."
    )
    return global_idx, float(x[global_idx]), float(y[global_idx]), note



def detect_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    cols = list(df.columns)
    lower = {c: str(c).strip().lower() for c in cols}

    def find_by_keywords(keywords: List[str]) -> Optional[str]:
        # First exact-ish match.
        for c, lc in lower.items():
            if any(k == lc for k in keywords):
                return c
        # Then substring match.
        for c, lc in lower.items():
            if any(k in lc for k in keywords):
                return c
        return None

    mapping = {
        "stage": find_by_keywords(["stage", "mode", "segment", "action", "test phase", "phase", "cycle", "步骤", "阶段", "模式"]),
        "time": find_by_keywords(["time", "time_s", "time (s)", "时间"]),
        "size": find_by_keywords(["size", "size_mm", "position", "position_mm", "位置"]),
        "disp": find_by_keywords(["displacement", "displacement_mm", "disp", "extension", "travel", "位移", "变形"]),
        "force": find_by_keywords(["force", "force_n", "load", "load_n", "force (n)", "load (n)", "力", "载荷"]),
    }
    return mapping


# -----------------------------
# Input parsers
# -----------------------------


def parse_sample_sheet_from_workbook(workbook_path: Path, sheet_name: str,
                                     default_span_mm: Optional[float],
                                     default_loading_rate: Optional[float]) -> Tuple[SampleMeta, pd.DataFrame]:
    df = pd.read_excel(workbook_path, sheet_name=sheet_name, header=None)

    # Extract key-value metrics from top block.
    meta_dict = {}
    for _, row in df.iloc[:32, :3].iterrows():
        key = row.iloc[0]
        val = row.iloc[1] if len(row) > 1 else None
        if pd.notna(key):
            meta_dict[str(key).strip()] = val

    sample_id = re.sub(r"\.csv$", "", str(meta_dict.get("File name", sheet_name)), flags=re.I)
    meta = SampleMeta(
        sample_id=sample_id,
        file_name=str(meta_dict.get("File name", sample_id)),
        length_mm=safe_float(meta_dict.get("Specimen length")),
        thickness_mm=safe_float(meta_dict.get("Center thickness")),
        span_mm=safe_float(meta_dict.get("Support span")) or default_span_mm,
        loading_rate_mm_min=safe_float(meta_dict.get("Loading rate")) or default_loading_rate,
    )

    # Find the raw-data header row.
    header_row = None
    for i in range(len(df)):
        row_vals = [str(v).strip() for v in df.iloc[i, :4].tolist() if pd.notna(v)]
        if len(row_vals) >= 2 and "Displacement_mm" in row_vals and "Force_N" in row_vals:
            header_row = i
            break
    if header_row is None:
        raise RuntimeError(f"Could not find raw-data table in sheet '{sheet_name}'")

    raw = pd.read_excel(workbook_path, sheet_name=sheet_name, header=header_row)
    raw.columns = [str(c).strip() for c in raw.columns]
    raw = raw.dropna(how="all")

    # Keep standard columns if present.
    cols_to_keep = [c for c in ["Time_S", "Size_mm", "Displacement_mm", "Force_N"] if c in raw.columns]
    if not cols_to_keep:
        cols_to_keep = list(raw.columns)
    raw = raw[cols_to_keep].copy()

    if "Displacement_mm" not in raw.columns or "Force_N" not in raw.columns:
        raise RuntimeError(f"Sheet '{sheet_name}' does not have Displacement_mm and Force_N columns")

    raw["Displacement_mm"] = pd.to_numeric(raw["Displacement_mm"], errors="coerce")
    raw["Force_N"] = pd.to_numeric(raw["Force_N"], errors="coerce")
    raw = raw.replace([np.inf, -np.inf], np.nan).dropna(subset=["Displacement_mm", "Force_N"]).copy()
    raw = raw.reset_index(drop=True)

    return meta, raw



def parse_workbook(workbook_path: Path,
                   default_span_mm: Optional[float],
                   default_loading_rate: Optional[float]) -> List[Tuple[SampleMeta, pd.DataFrame]]:
    xls = pd.ExcelFile(workbook_path)
    ignore = {"summary", "how_it_was_done"}
    sample_sheets = [s for s in xls.sheet_names if s.strip().lower() not in ignore]
    items = []
    for sheet in sample_sheets:
        meta, raw = parse_sample_sheet_from_workbook(workbook_path, sheet, default_span_mm, default_loading_rate)
        items.append((meta, raw))
    return items



def parse_csv_folder(input_dir: Path, metadata_path: Optional[Path],
                     default_span_mm: Optional[float],
                     default_loading_rate: Optional[float]) -> List[Tuple[SampleMeta, pd.DataFrame]]:
    meta_df = None
    if metadata_path is not None:
        meta_df = pd.read_csv(metadata_path)
        meta_df.columns = [str(c).strip() for c in meta_df.columns]

    csv_files = sorted(input_dir.glob("*.csv"))
    if not csv_files:
        raise RuntimeError(f"No CSV files found in {input_dir}")

    items = []
    for csv_path in csv_files:
        df = read_csv_flexible(csv_path)
        mapping = detect_columns(df)

        if mapping["disp"] is None or mapping["force"] is None:
            raise RuntimeError(
                f"Could not detect displacement/force columns in {csv_path.name}. Columns: {list(df.columns)}"
            )

        stage_col = mapping["stage"]
        if stage_col is not None:
            stage_series = df[stage_col].astype(str).str.lower()
            compress_mask = stage_series.str.contains("compress")
            if compress_mask.any():
                df = df.loc[compress_mask].copy()

        out = pd.DataFrame()
        if mapping["time"] is not None:
            out["Time_S"] = pd.to_numeric(df[mapping["time"]], errors="coerce")
        if mapping["size"] is not None:
            out["Size_mm"] = pd.to_numeric(df[mapping["size"]], errors="coerce")
        out["Displacement_mm"] = pd.to_numeric(df[mapping["disp"]], errors="coerce")
        out["Force_N"] = pd.to_numeric(df[mapping["force"]], errors="coerce")
        out = out.replace([np.inf, -np.inf], np.nan).dropna(subset=["Displacement_mm", "Force_N"]).copy()
        out = out.reset_index(drop=True)

        sample_id = csv_path.stem
        row = None
        if meta_df is not None:
            # Try sample_id first, then file_name, then csv_path stem.
            candidates = []
            if "sample_id" in meta_df.columns:
                candidates.append(meta_df["sample_id"].astype(str) == sample_id)
            if "file_name" in meta_df.columns:
                candidates.append(meta_df["file_name"].astype(str).str.replace(r"\\.csv$", "", regex=True) == sample_id)
            if "csv_path" in meta_df.columns:
                candidates.append(meta_df["csv_path"].astype(str).apply(lambda p: Path(p).stem) == sample_id)
            mask = None
            for m in candidates:
                mask = m if mask is None else (mask | m)
            if mask is not None and mask.any():
                row = meta_df.loc[mask].iloc[0]

        meta = SampleMeta(
            sample_id=sample_id if row is None or "sample_id" not in row.index else str(row.get("sample_id")),
            file_name=csv_path.name,
            length_mm=None if row is None else safe_float(row.get("length_mm")),
            thickness_mm=None if row is None else safe_float(row.get("thickness_mm")),
            span_mm=default_span_mm if row is None else (safe_float(row.get("span_mm")) or default_span_mm),
            loading_rate_mm_min=default_loading_rate if row is None else (safe_float(row.get("loading_rate_mm_min")) or default_loading_rate),
            linear_start_mm=None if row is None else safe_float(row.get("linear_start_mm")),
            linear_end_mm=None if row is None else safe_float(row.get("linear_end_mm")),
        )
        items.append((meta, out))

    return items




def read_csv_with_header_detection(path: Path) -> pd.DataFrame:
    errors = []
    for encoding in ("utf-8-sig", "gb18030", "utf-16", "latin1"):
        try:
            text = path.read_text(encoding=encoding)
        except (UnicodeError, OSError):
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines[:60]):
            for sep in (",", ";", "\t"):
                cols = next(csv.reader([line], delimiter=sep))
                mapping = detect_columns(pd.DataFrame(columns=cols))
                if mapping["disp"] is None or mapping["force"] is None or mapping["disp"] == mapping["force"]:
                    continue
                try:
                    df = pd.read_csv(io.StringIO("\n".join(lines[i:])), sep=sep)
                    for kind in ("disp", "force"):
                        label = str(mapping[kind]).lower()
                        bad = r"kn|kgf|lbf|lbs|磅|千牛|公斤" if kind == "force" else r"inch|\bin\b|cm|um|μm|µm|厘米|微米"
                        if re.search(bad, label):
                            raise ValueError("Unsupported units: convert displacement to mm and force to N first.")
                    return df
                except ValueError as exc:
                    if "Unsupported units" in str(exc):
                        raise
                    errors.append(str(exc))
    raise ValueError(f"No valid displacement/force header found in {path.name} (first 60 rows).")


def _load_metadata_table(metadata_path: Optional[Path]) -> Optional[pd.DataFrame]:
    if metadata_path is None:
        return None
    if not metadata_path.exists():
        raise FileNotFoundError(f"Metadata CSV not found: {metadata_path}")
    df = read_csv_flexible(metadata_path)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _metadata_row_for_file(meta_df: Optional[pd.DataFrame], root_dir: Path, csv_path: Path):
    if meta_df is None or meta_df.empty:
        return None

    rel_file = csv_path.relative_to(root_dir).as_posix()
    rel_folder = csv_path.parent.relative_to(root_dir).as_posix()
    folder_name = csv_path.parent.name
    stem = csv_path.stem

    tiers = [
        [("relative_path", [rel_file]), ("csv_path", [rel_file])],
        [("relative_folder", [rel_folder]), ("folder", [rel_folder]), ("sample_folder", [rel_folder])],
        [("file_name", [csv_path.name, stem]), ("csv_path", [csv_path.name])],
        [("sample_id", [folder_name, stem]), ("folder", [folder_name])],
    ]
    for tier in tiers:
        mask = pd.Series(False, index=meta_df.index)
        for col, values in tier:
            if col in meta_df.columns:
                v = meta_df[col].astype(str).str.strip().str.replace("\\", "/", regex=False).str.lower()
                mask |= v.isin([str(x).lower() for x in values])
        if mask.sum() > 1:
            raise ValueError(f"Ambiguous metadata for {rel_file}; use a unique relative_path.")
        if mask.any():
            return meta_df.loc[mask].iloc[0]
    return None


def parse_nested_csv_root(root_dir: Path,
                          metadata_path: Optional[Path],
                          default_span_mm: Optional[float],
                          default_loading_rate: Optional[float],
                          default_thickness_mm: Optional[float] = None,
                          default_length_mm: Optional[float] = None,
                          output_dir: Optional[Path] = None) -> Tuple[List[Tuple[SampleMeta, pd.DataFrame]], pd.DataFrame]:
    """
    Recursively scan a selected root directory.

    Expected layout (other files are ignored):
        ROOT/
          sample_A/
            data.csv
            image.jpg
            notes.txt
          sample_B/
            data.csv
            ...

    Every CSV that contains recognizable displacement + force columns is treated
    as a three-point-bending data file. Invalid/irrelevant CSV files are skipped
    and recorded in scan_report.csv.
    """
    root_dir = root_dir.resolve()
    meta_df = _load_metadata_table(metadata_path)
    output_resolved = output_dir.resolve() if output_dir is not None else None
    metadata_resolved = metadata_path.resolve() if metadata_path is not None else None

    csv_files = sorted(p for p in root_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".csv")
    items: List[Tuple[SampleMeta, pd.DataFrame]] = []
    report_rows = []
    used_sample_ids = set()

    for csv_path in csv_files:
        try:
            rp = csv_path.resolve()
            if metadata_resolved is not None and rp == metadata_resolved:
                report_rows.append({"relative_path": csv_path.relative_to(root_dir).as_posix(), "status": "SKIPPED", "reason": "metadata CSV"})
                continue
            if output_resolved is not None:
                try:
                    rp.relative_to(output_resolved)
                    report_rows.append({"relative_path": csv_path.relative_to(root_dir).as_posix(), "status": "SKIPPED", "reason": "inside output folder"})
                    continue
                except ValueError:
                    pass

            df = read_csv_with_header_detection(csv_path)
            mapping = detect_columns(df)
            if mapping["disp"] is None or mapping["force"] is None:
                raise RuntimeError("No displacement/force columns detected")

            stage_col = mapping["stage"]
            if stage_col is not None:
                stage_series = df[stage_col].astype(str).str.strip().str.lower()
                compress_mask = stage_series.str.contains("compress|compression|压缩", regex=True, na=False)
                if compress_mask.any():
                    df = df.loc[compress_mask].copy()

            out = pd.DataFrame()
            if mapping["time"] is not None:
                out["Time_S"] = pd.to_numeric(df[mapping["time"]], errors="coerce")
            if mapping["size"] is not None:
                out["Size_mm"] = pd.to_numeric(df[mapping["size"]], errors="coerce")
            out["Displacement_mm"] = pd.to_numeric(df[mapping["disp"]], errors="coerce")
            out["Force_N"] = pd.to_numeric(df[mapping["force"]], errors="coerce")
            out = out.replace([np.inf, -np.inf], np.nan).dropna(subset=["Displacement_mm", "Force_N"]).copy()
            out = out.reset_index(drop=True)
            if len(out) < 5:
                raise RuntimeError(f"Only {len(out)} usable data rows")

            rel_folder = csv_path.parent.relative_to(root_dir).as_posix()
            row = _metadata_row_for_file(meta_df, root_dir, csv_path)

            # Folder name is the preferred sample name for the requested layout.
            base_id = csv_path.parent.name if csv_path.parent != root_dir else csv_path.stem
            if row is not None and "sample_id" in row.index and pd.notna(row.get("sample_id")):
                base_id = str(row.get("sample_id")).strip()

            sample_id = base_id
            if sample_id in used_sample_ids:
                sample_id = f"{base_id}__{csv_path.stem}"
                n = 2
                while sample_id in used_sample_ids:
                    sample_id = f"{base_id}__{csv_path.stem}_{n}"
                    n += 1
            used_sample_ids.add(sample_id)

            def rv(col, default=None):
                if row is None or col not in row.index:
                    return default
                val = safe_float(row.get(col))
                return default if val is None else val

            meta = SampleMeta(
                sample_id=sample_id,
                file_name=csv_path.name,
                length_mm=rv("length_mm", default_length_mm),
                thickness_mm=rv("thickness_mm", default_thickness_mm),
                span_mm=rv("span_mm", default_span_mm),
                loading_rate_mm_min=rv("loading_rate_mm_min", default_loading_rate),
                linear_start_mm=rv("linear_start_mm", None),
                linear_end_mm=rv("linear_end_mm", None),
                relative_folder=rel_folder,
            )
            items.append((meta, out))
            report_rows.append({
                "relative_path": csv_path.relative_to(root_dir).as_posix(),
                "sample_id": sample_id,
                "status": "READY",
                "reason": "valid force-displacement CSV; units must be mm and N",
                "rows": len(out),
            })
        except Exception as exc:
            try:
                rel = csv_path.relative_to(root_dir).as_posix()
            except Exception:
                rel = str(csv_path)
            report_rows.append({"relative_path": rel, "status": "SKIPPED", "reason": str(exc)})

    report = pd.DataFrame(report_rows)
    if not items:
        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            report.to_csv(output_dir / "scan_report.csv", index=False, encoding="utf-8-sig")
        raise RuntimeError(
            "No valid force-displacement CSV files were found under the selected root folder. "
            "The program looks for columns such as Displacement_mm/Displacement and Force_N/Force."
        )
    return items, report

# -----------------------------
# Core analysis
# -----------------------------


def analyze_force_displacement(meta: SampleMeta, raw: pd.DataFrame,
                               offset_strain: float = 0.002,
                               yield_method: str = "three_pb",
                               offset_displacement_mm: Optional[float] = None,
                               max_displacement_offset_fraction: float = 0.002,
                               stiffness_loss_fraction: float = 0.0) -> Tuple[AnalysisResult, Dict[str, np.ndarray]]:
    """Analyze one monotonic force-displacement curve.

    Yield modes exposed by the GUI:
    - ``three_pb`` reproduces the SoftwareX 3PB-Analyzer rule:
      y_ref = YFC * K * (x - xmax * dispc) + b,
      where YFC = 1 - stiffness_loss_fraction. Starting immediately after the
      fitted linear window, the first sampled point satisfying
      0.8*y_ref <= F <= y_ref is the yield point. If no such point exists, the
      last point of the fitted linear window is used, matching the published
      fallback rule.
    - ``strain`` uses a flexural-strain offset converted to displacement with
      delta = epsilon * L^2 / (6h), then finds the first line/curve crossing.

    ``displacement`` and ``none`` remain accepted for backward compatibility
    with older command-line workflows but are not exposed in the current GUI.
    """
    df = raw.copy().reset_index(drop=True)
    x = df["Displacement_mm"].to_numpy(dtype=float)
    y = df["Force_N"].to_numpy(dtype=float)

    if len(x) < 5 or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("Need at least 5 finite displacement/force rows.")
    if np.any(np.diff(x) < -1e-9):
        raise ValueError("Displacement decreases in acquisition order. Select one monotonic Compress segment; data were not sorted.")
    if np.ptp(x) <= 0:
        raise ValueError("Displacement has no range.")

    # Analysis coordinates remain independent of display cropping. The plotting
    # layer may re-zero the visible x-axis without changing scientific results.
    x = x - x[0]
    df["Displacement_mm"] = x

    if yield_method == "auto":
        yield_method = "strain" if compute_offset_displacement(meta, offset_strain) is not None else "three_pb"
    if yield_method not in ("three_pb", "strain", "displacement", "none"):
        raise ValueError("Unknown yield method.")

    # Peak / max force.
    peak_idx = int(np.argmax(y))
    if peak_idx < 2:
        raise ValueError("Peak occurs too early to fit a pre-peak stiffness region.")
    max_force = float(y[peak_idx])
    max_disp = float(x[peak_idx])
    recorded_max_disp = float(np.max(x))

    # Stiffness.
    lin_i, lin_j, stiffness, intercept, r2 = find_best_linear_region(
        x, y, peak_idx,
        manual_start=meta.linear_start_mm,
        manual_end=meta.linear_end_mm,
    )

    notes = []
    if not np.isfinite(stiffness) or stiffness <= 0:
        raise ValueError("A positive finite stiffness could not be fitted.")

    delta_offset = float("nan")
    y_offset = np.full_like(x, np.nan)
    yield_disp = yield_force = float("nan")
    yield_source_index = -1

    if yield_method == "three_pb":
        if (not math.isfinite(max_displacement_offset_fraction)
                or max_displacement_offset_fraction < 0):
            raise ValueError("3PB max-displacement offset must be a non-negative finite fraction.")
        if (not math.isfinite(stiffness_loss_fraction)
                or stiffness_loss_fraction < 0 or stiffness_loss_fraction >= 1):
            raise ValueError("Stiffness loss must be a finite fraction from 0 (inclusive) to 1 (exclusive).")

        # SoftwareX 3PB-Analyzer equation:
        # y_ref = YFC * a * (x - maxdisp * dispc) + b
        yfc = 1.0 - stiffness_loss_fraction
        delta_offset = recorded_max_disp * max_displacement_offset_fraction
        y_offset = yfc * stiffness * (x - delta_offset) + intercept

        # Published special case / fallback: if the fitted window ends at the
        # maximum, or no qualifying point is found, use the final fit point.
        if math.isclose(float(y[lin_j]), max_force, rel_tol=0.0, abs_tol=1e-12):
            yield_source_index = lin_j
        else:
            for idx in range(lin_j + 1, len(x)):
                ref = float(y_offset[idx])
                actual = float(y[idx])
                if math.isfinite(ref) and 0.8 * ref <= actual <= ref:
                    yield_source_index = idx
                    break
            if yield_source_index < 0:
                yield_source_index = lin_j
                notes.append("3PB-Analyzer fallback: no qualifying post-fit yield point; final linear-fit point used.")

        yield_disp = float(x[yield_source_index])
        yield_force = float(y[yield_source_index])
        notes.append(
            "Yield method: 3PB-Analyzer; "
            f"max-displacement offset={100*max_displacement_offset_fraction:g}%, "
            f"stiffness loss={100*stiffness_loss_fraction:g}%."
        )

    elif yield_method == "strain":
        if not math.isfinite(offset_strain) or offset_strain <= 0:
            raise ValueError("Strain offset must be positive and finite.")
        delta_offset = compute_offset_displacement(meta, offset_strain)
        if delta_offset is None:
            raise ValueError("Flexural strain-offset yield requires positive specimen depth/thickness h and support span L.")
        y_offset = stiffness * (x - delta_offset) + intercept
        inter = find_first_intersection(x, y, y_offset, start_idx=lin_j)
        if inter is None:
            notes.append("No strain-offset line intersection; yield is unavailable.")
        else:
            yield_disp, yield_force = inter
        notes.append(f"Yield method: flexural strain offset {100*offset_strain:g}%.")

    elif yield_method == "displacement":
        if offset_displacement_mm is None or not math.isfinite(offset_displacement_mm) or offset_displacement_mm <= 0:
            raise ValueError("Enter a positive finite displacement offset in mm.")
        delta_offset = offset_displacement_mm
        y_offset = stiffness * (x - delta_offset) + intercept
        inter = find_first_intersection(x, y, y_offset, start_idx=lin_j)
        if inter is not None:
            yield_disp, yield_force = inter
        notes.append(f"Yield method: legacy displacement offset {delta_offset:g} mm.")

    else:
        notes.append("Yield calculation disabled; yield and postyield results are blank.")

    # Fracture point.
    frac_idx, frac_disp, frac_force, frac_note = find_fracture_point(x, y, peak_idx)
    notes.append(frac_note)

    postyield_disp = float(max(0.0, frac_disp - yield_disp)) if math.isfinite(yield_disp) else float("nan")

    # Work to fracture.
    x_work = x[:frac_idx + 1]
    y_work = np.maximum(y[:frac_idx + 1], 0.0)
    work = float(np.trapezoid(y_work, x_work) if hasattr(np, "trapezoid") else np.trapz(y_work, x_work))

    result = AnalysisResult(
        sample_id=meta.sample_id,
        file_name=meta.file_name,
        relative_folder=meta.relative_folder,
        length_mm=meta.length_mm,
        thickness_mm=meta.thickness_mm,
        span_mm=meta.span_mm,
        loading_rate_mm_min=meta.loading_rate_mm_min,
        max_force_n=max_force,
        max_force_disp_mm=max_disp,
        stiffness_n_per_mm=float(stiffness),
        stiffness_r2=float(r2),
        stiffness_intercept_n=float(intercept),
        yield_force_n=float(yield_force),
        yield_disp_mm=float(yield_disp),
        postyield_disp_mm=float(postyield_disp),
        fracture_force_n=float(frac_force),
        fracture_disp_mm=float(frac_disp),
        fracture_strain_pct=None,
        work_to_fracture_n_mm=float(work),
        notes=" ".join(notes).strip(),
    )

    debug = {
        "x": x,
        "y": y,
        "peak_idx": np.array([peak_idx]),
        "lin_i": np.array([lin_i]),
        "lin_j": np.array([lin_j]),
        "y_offset": y_offset,
        "delta_offset": np.array([delta_offset]),
        "yield_method": yield_method,
        "offset_strain": offset_strain,
        "max_displacement_offset_fraction": max_displacement_offset_fraction,
        "stiffness_loss_fraction": stiffness_loss_fraction,
        "yield_force_constant": 1.0 - stiffness_loss_fraction,
        "recorded_max_displacement_mm": recorded_max_disp,
        "yield_source_index": np.array([yield_source_index]),
    }
    return result, debug


def analyze_one_sample(meta: SampleMeta, raw: pd.DataFrame,
                       include_fracture_strain: bool,
                       offset_strain: float = 0.002,
                       yield_method: str = "three_pb",
                       offset_displacement_mm: Optional[float] = None,
                       max_displacement_offset_fraction: float = 0.002,
                       stiffness_loss_fraction: float = 0.0) -> Tuple[AnalysisResult, Dict[str, np.ndarray]]:
    result, debug = analyze_force_displacement(
        meta, raw, offset_strain, yield_method, offset_displacement_mm,
        max_displacement_offset_fraction=max_displacement_offset_fraction,
        stiffness_loss_fraction=stiffness_loss_fraction,
    )
    if include_fracture_strain:
        if meta.thickness_mm is not None and meta.span_mm is not None and meta.thickness_mm > 0 and meta.span_mm > 0:
            result = replace(result, fracture_strain_pct=float(
                6 * meta.thickness_mm * result.fracture_disp_mm / (meta.span_mm ** 2) * 100))
        else:
            result = replace(result, notes=result.notes + " Fracture strain unavailable: positive specimen depth/thickness h and span L required; mechanical results retained.")
    return result, debug


def format_num(v: Optional[float], digits: int = 3) -> str:
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "NA"
    return f"{v:.{digits}f}"



from bending_plotting import PlotOptions, plot_one_sample, plot_overlay


def write_outputs(results: List[AnalysisResult], raw_map: Dict[str, pd.DataFrame],
                  debug_map: Dict[str, Dict[str, np.ndarray]], output_dir: Path,
                  include_fracture_strain: bool, plot_options: Optional[PlotOptions] = None) -> None:
    plot_options = (plot_options or PlotOptions()).validate()
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_dir = output_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)

    # Summary table.
    summary_rows = []
    for res in results:
        row = {
            "File name": res.sample_id,
            "Relative folder": res.relative_folder,
            "Source CSV": res.file_name,
            "Length (mm)": res.length_mm,
            "Center thickness (mm)": res.thickness_mm,
            "Support span (mm)": res.span_mm,
            "Max Force (N)": res.max_force_n,
            "Stiffness (N/mm)": res.stiffness_n_per_mm,
            "Yield force (N)": res.yield_force_n,
            "Yield displacement (mm)": res.yield_disp_mm,
            "Postyield Displacement (mm)": res.postyield_disp_mm,
            "Fracture displacement (mm)": res.fracture_disp_mm,
            "Fracture force (N)": res.fracture_force_n,
            "Work to fracture (N·mm)": res.work_to_fracture_n_mm,
            "Stiffness R²": res.stiffness_r2,
        }
        if include_fracture_strain:
            row["Fracture strain (%)"] = res.fracture_strain_pct
        row["Notes"] = res.notes
        summary_rows.append(row)
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(output_dir / "summary.csv", index=False, encoding="utf-8-sig")

    # Generate figures before embedding them in Excel.
    plot_options.save(output_dir / "plot_settings.json")
    plot_paths = {}
    plot_reports = []
    for idx, res in enumerate(results, 1):
        name = re.sub(r"[^\w.+-]", "_", res.sample_id)[:80]
        pp = plot_dir / f"{idx:03d}_{name}_force_displacement.png"
        report = plot_one_sample(res, raw_map[res.sample_id], debug_map[res.sample_id], pp, include_fracture_strain, plot_options)
        plot_reports.append({"sample_id": res.sample_id, **report})
        plot_paths[res.sample_id] = pp
    plot_overlay(results, raw_map, plot_dir / "all_samples_overlay.png", plot_options, debug_map)
    pd.DataFrame(plot_reports).to_csv(output_dir / "plot_display_report.csv", index=False, encoding="utf-8-sig")

    # Excel workbook.
    xlsx_path = output_dir / "three_point_bending_results.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)

        how_df = pd.DataFrame({
            "Item": [
                "Graph type",
                "Max Force",
                "Stiffness",
                "Yield point",
                "Fracture point",
                "Postyield displacement",
                "Work to fracture",
                "Fracture strain",
            ],
            "How it is generated": [
                "Plot Force_N versus Displacement_mm.",
                "Highest force on the curve.",
                "Slope of selected/auto-detected pre-peak linear region.",
                "3PB-Analyzer mode: y_ref=(1-loss)×K×[x−xmax×offset]+b; after the fit window, the first sampled point with 0.8×y_ref ≤ F ≤ y_ref is Yield; if none, the final fit point is used. Flexural strain-offset mode uses εoffset×L²/(6h) and the first curve/offset-line intersection.",
                "Point immediately before the largest post-peak force drop.",
                "Fracture displacement − Yield displacement.",
                "Trapezoidal area under the force-displacement curve up to fracture.",
                "6×h×δf / L² × 100%, only when enabled and dimensions are available.",
            ]
        })
        if not include_fracture_strain:
            how_df = how_df[how_df["Item"] != "Fracture strain"]
        how_df.to_excel(writer, sheet_name="How_it_was_done", index=False)
        used_sheets = {"summary", "how_it_was_done"}

        for res in results:
            raw = raw_map[res.sample_id].copy()
            raw = raw.reset_index(drop=True)
            raw["Displacement_original_mm"] = raw["Displacement_mm"]
            raw["Displacement_mm"] = raw["Displacement_mm"] - raw["Displacement_mm"].iloc[0]
            if include_fracture_strain:
                raw["Apparent_strain_pct"] = (6*res.thickness_mm*raw["Displacement_mm"]/(res.span_mm**2)*100
                                              if res.fracture_strain_pct is not None else np.nan)

            metrics_rows = [
                ["File name", res.file_name, "source file"],
                ["Relative folder", res.relative_folder, "source folder"],
                ["Specimen length", res.length_mm, "mm"],
                ["Center thickness", res.thickness_mm, "mm"],
                ["Support span", res.span_mm, "mm"],
                ["Loading rate", res.loading_rate_mm_min, "mm/min"],
                ["Max Force", res.max_force_n, "N"],
                ["Max Force displacement", res.max_force_disp_mm, "mm"],
                ["Stiffness", res.stiffness_n_per_mm, "N/mm"],
                ["Stiffness R²", res.stiffness_r2, "fit quality"],
                ["Yield force", res.yield_force_n, "N"],
                ["Yield displacement", res.yield_disp_mm, "mm"],
                ["Postyield Displacement", res.postyield_disp_mm, "mm"],
                ["Fracture force", res.fracture_force_n, "N"],
                ["Fracture displacement", res.fracture_disp_mm, "mm"],
                ["Fracture strain", res.fracture_strain_pct if include_fracture_strain else None, "%" if include_fracture_strain else "not calculated"],
                ["Work to fracture", res.work_to_fracture_n_mm, "N·mm"],
                ["Notes", res.notes, ""],
            ]
            metrics_df = pd.DataFrame(metrics_rows, columns=["Parameter", "Value", "Unit / note"])
            if not include_fracture_strain:
                metrics_df = metrics_df[metrics_df["Parameter"] != "Fracture strain"]
            sheet_name = sanitize_sheet_name(res.sample_id).strip("'") or "Sample"
            base = sheet_name
            n = 2
            while sheet_name.lower() in used_sheets:
                suffix = f"_{n}"
                sheet_name = base[:31-len(suffix)] + suffix
                n += 1
            used_sheets.add(sheet_name.lower())
            metrics_df.to_excel(writer, sheet_name=sheet_name, startrow=0, index=False)
            raw.to_excel(writer, sheet_name=sheet_name, startrow=len(metrics_df) + 3, index=False)

            from openpyxl.drawing.image import Image
            ws = writer.book[sheet_name]
            img = Image(str(plot_paths[res.sample_id])); img.width = 840; img.height = 459.375
            ws.add_image(img, "F2")
            ws.column_dimensions["A"].width = 29
            ws.column_dimensions["B"].width = 24
            ws.column_dimensions["C"].width = 24
            # Long notes occupy a separate wrapped row below the metric values.
            nr = 1 + list(metrics_df["Parameter"]).index("Notes") + 1
            ws.cell(nr, 2).alignment = __import__("openpyxl").styles.Alignment(wrap_text=True, vertical="top")
            ws.row_dimensions[nr].height = 100
            ws.column_dimensions["D"].width = 22
            ws.column_dimensions["E"].width = 25
            ws.freeze_panes = "B2"

        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        thin = Side(style="thin", color="B7B7B7")
        table_border = Border(left=thin, right=thin, top=thin, bottom=thin)
        centered = Alignment(horizontal="center", vertical="center", wrap_text=True)

        for ws in writer.book:
            # User-facing tables keep visible worksheet gridlines and explicit cell borders.
            ws.sheet_view.showGridLines = True

            # Apply a complete cell grid plus horizontal/vertical centering
            # across the entire used table area, including blank cells inside it.
            for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
                for cell in row:
                    cell.alignment = centered
                    cell.border = table_border
                    if isinstance(cell.value, (int, float)):
                        cell.number_format = "0.0000"

            # Header row formatting.
            for cell in ws[1]:
                if cell.value is not None:
                    cell.font = Font(name="Calibri", bold=True, color="FFFFFF")
                    cell.fill = PatternFill("solid", fgColor="214C70")
                    cell.alignment = centered
                    cell.border = table_border
            ws.row_dimensions[1].height = 34

            if ws.title == "Summary":
                ws.freeze_panes = "B2"
                ws.auto_filter.ref = ws.dimensions
                for j in range(1, ws.max_column + 1):
                    ws.column_dimensions[get_column_letter(j)].width = 22 if j < ws.max_column else 65
                for j in range(2, ws.max_row + 1):
                    ws.row_dimensions[j].height = 58

            if ws.title == "How_it_was_done":
                ws.column_dimensions["A"].width = 28
                ws.column_dimensions["B"].width = 105
                for j in range(2, ws.max_row + 1):
                    ws.row_dimensions[j].height = 52


# -----------------------------
# Main
# -----------------------------

def swap_model_o(items):
    """Swap specimen identities only; measurements and geometry travel together.

    Source filename/folder stay unchanged for provenance. This operation is
    explicit and must not be applied to already corrected folder names.
    """
    from dataclasses import replace
    pairs = [("model001data", "o001data"), ("model", "o")]
    lookup = {m.sample_id.casefold(): i for i, (m, _) in enumerate(items)}
    pair = next(((a, b) for a, b in pairs if a in lookup and b in lookup), None)
    if pair is None:
        raise ValueError("Expected exactly one model/O or model001Data/O001Data pair; edit sample names directly if different.")
    a, b = (lookup[x] for x in pair)
    output = list(items)
    ma, ra = items[a]; mb, rb = items[b]
    output[a] = (replace(ma, sample_id=mb.sample_id), ra)
    output[b] = (replace(mb, sample_id=ma.sample_id), rb)
    return output


def save_run_config(items, output_dir, options):
    """Save the exact per-sample settings, file mapping and curve digest used."""
    records = []
    for m, raw in items:
        row = asdict(m)
        row["processed_curve_sha256"] = hashlib.sha256(raw.to_csv(index=False).encode("utf-8")).hexdigest()
        records.append(row)
    payload = {"version": "4.3", "options": options, "samples": records}
    (Path(output_dir)/"run_config.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame([asdict(m) for m, _ in items]).to_csv(Path(output_dir)/"sample_parameters_used.csv", index=False, encoding="utf-8-sig")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Three-point bending analysis with optional fracture strain and plot generation.")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--input-workbook", type=str, help="Path to an Excel workbook containing sample sheets.")
    group.add_argument("--input-dir", type=str, help="Directory containing raw CSV files directly.")
    group.add_argument("--root-dir", type=str, help="Root directory containing multiple sample subfolders; CSV files are discovered recursively.")
    p.add_argument("--metadata", type=str, default=None, help="Optional metadata CSV for CSV folder mode.")
    p.add_argument("--output-dir", type=str, required=True, help="Output directory.")
    p.add_argument("--include-fracture-strain", choices=["yes", "no"], default="yes",
                   help="Whether to calculate fracture strain.")
    p.add_argument("--default-span-mm", type=float, default=7.0, help="Default support span in mm.")
    p.add_argument("--default-loading-rate", type=float, default=3.0, help="Default loading rate in mm/min.")
    p.add_argument("--default-thickness-mm", type=float, default=None, help="Optional default center thickness for fracture strain.")
    p.add_argument("--default-length-mm", type=float, default=None, help="Optional specimen length for reporting.")
    p.add_argument("--offset-strain", type=float, default=0.002, help="Flexural strain offset as a fraction (default: 0.002 = 0.2%%).")
    p.add_argument("--yield-method", choices=["three_pb", "strain", "auto", "displacement", "none"], default="three_pb")
    p.add_argument("--max-displacement-offset-pct", type=float, default=0.2,
                   help="3PB-Analyzer displacement constant as percent of recorded maximum displacement (default: 0.2).")
    p.add_argument("--stiffness-loss-pct", type=float, default=0.0,
                   help="3PB-Analyzer stiffness loss percent; YFC=1-loss/100 (default: 0).")
    p.add_argument("--offset-displacement-mm", type=float, default=None,
                   help="Legacy absolute displacement offset; retained for compatibility only.")
    p.add_argument("--swap-model-o", action="store_true", help="Explicitly correct the misnamed model/O pair; never enabled automatically.")
    p.add_argument("--plot-settings", type=str, default=None, help="Plot settings JSON exported from the GUI.")
    return p



def main() -> None:
    args = build_arg_parser().parse_args()
    output_dir = Path(args.output_dir)
    include_fracture_strain = args.include_fracture_strain.lower() == "yes"

    scan_report = None
    if args.input_workbook:
        items = parse_workbook(Path(args.input_workbook), args.default_span_mm, args.default_loading_rate)
    elif args.root_dir:
        items, scan_report = parse_nested_csv_root(
            Path(args.root_dir),
            Path(args.metadata) if args.metadata else None,
            args.default_span_mm,
            args.default_loading_rate,
            args.default_thickness_mm,
            args.default_length_mm,
            output_dir,
        )
    else:
        items = parse_csv_folder(Path(args.input_dir), Path(args.metadata) if args.metadata else None,
                                 args.default_span_mm, args.default_loading_rate)

    if args.swap_model_o:
        items = swap_model_o(items)

    results: List[AnalysisResult] = []
    raw_map: Dict[str, pd.DataFrame] = {}
    debug_map: Dict[str, Dict[str, np.ndarray]] = {}

    for meta, raw in items:
        res, dbg = analyze_one_sample(
            meta, raw, include_fracture_strain,
            offset_strain=args.offset_strain,
            yield_method=args.yield_method,
            offset_displacement_mm=args.offset_displacement_mm,
            max_displacement_offset_fraction=args.max_displacement_offset_pct / 100.0,
            stiffness_loss_fraction=args.stiffness_loss_pct / 100.0,
        )
        results.append(res)
        raw_map[meta.sample_id] = raw
        debug_map[meta.sample_id] = dbg

    write_outputs(results, raw_map, debug_map, output_dir, include_fracture_strain, PlotOptions.load(args.plot_settings) if args.plot_settings else PlotOptions())
    save_run_config(items, output_dir, vars(args))
    if scan_report is not None:
        scan_report.loc[scan_report["status"] == "READY", "status"] = "ANALYZED"
        scan_report.to_csv(output_dir / "scan_report.csv", index=False, encoding="utf-8-sig")

    print(f"Done. Results saved to: {output_dir}")
    print(f"- Summary CSV: {output_dir / 'summary.csv'}")
    print(f"- Summary Excel: {output_dir / 'three_point_bending_results.xlsx'}")
    print(f"- Plot folder: {output_dir / 'plots'}")


if __name__ == "__main__":
    main()
