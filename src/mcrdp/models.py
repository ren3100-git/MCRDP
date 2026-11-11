from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from mcrdp.profiles import SOFTWARE_PROFILES, SoftwareProfile


NAME_MAP_COLUMNS = ["export", "n_points", "variable_key", "internal_name", "output_name"]
NAME_TABLE_COLUMNS = [
    "export",
    "n_points",
    "variable_key",
    "mean_header",
    "internal_name",
    "output_name",
]
COLUMN_INFO_COLUMNS = ["internal_name", "header_variable", "mean_value"]


@dataclass
class ProcessorConfig:
    name_order: str = "var-num-name"
    log10_vars: list[str] = field(default_factory=list)
    linear_vars: list[str] = field(default_factory=list)
    mean_variable: str | None = None


@dataclass(frozen=True)
class FileReport:
    path: Path
    software: str
    encoding: str
    status: str
    message: str = ""


@dataclass(frozen=True)
class DetectedInput:
    software: str
    profile: SoftwareProfile
    encoding: str
    df_raw: pd.DataFrame
    score: int


@dataclass
class ProcessResult:
    original: pd.DataFrame
    variables: pd.DataFrame
    data_name_set: list[dict[str, str]]
    processed_files: list[Path]
    mean_variable: str | None = None
    name_map: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=NAME_MAP_COLUMNS)
    )
    column_info: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=COLUMN_INFO_COLUMNS)
    )
    file_reports: list[FileReport] = field(default_factory=list)

    @property
    def format_counts(self) -> dict[str, int]:
        counts = {name: 0 for name in SOFTWARE_PROFILES}
        for report in self.file_reports:
            if report.software in counts:
                counts[report.software] += 1
        return counts

    @property
    def skipped_reports(self) -> list[FileReport]:
        return [report for report in self.file_reports if report.status != "processed"]
