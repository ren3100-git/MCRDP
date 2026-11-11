from __future__ import annotations

from pathlib import Path

import pandas as pd

from mcrdp.models import ProcessResult
from mcrdp.processor import RheoDataProcessor


class ExcelExporter:
    """Write processed application data to the MCRDP Excel workbook format."""

    def __init__(self, processor: RheoDataProcessor):
        self.processor = processor

    @staticmethod
    def make_igor_command_sheet(igor_command: str | None) -> pd.DataFrame:
        text = (igor_command or "IGOR command was not generated.").strip()
        if not text:
            text = "IGOR command was not generated."
        lines = text.splitlines()
        return pd.DataFrame({
            "line_no": list(range(1, len(lines) + 1)),
            "command": lines,
        })

    def export(
        self,
        result: ProcessResult,
        output_path: str | Path = "merged_sorted.xlsx",
        *,
        use_output_names: bool = True,
        include_original: bool = True,
        include_name_map: bool = True,
        igor_command: str | None = None,
        include_igor_command: bool = True,
    ) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # variables sheet:
        # row 1: mean of the GUI-selected variable, or blank when not selected
        # row 2: base variable key
        # row 3: output_name
        # row 4+: data
        variables = (
            self.processor.variables_with_export_headers(result)
            if use_output_names
            else result.variables
        )

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            if include_original:
                result.original.to_excel(
                    writer,
                    sheet_name="original",
                    index=False,
                    header=False,
                )
            variables.to_excel(
                writer,
                sheet_name="variables",
                index=False,
                header=False,
            )
            if include_name_map:
                result.name_map.to_excel(
                    writer,
                    sheet_name="name_map",
                    index=False,
                    header=True,
                )
            if include_igor_command:
                self.make_igor_command_sheet(igor_command).to_excel(
                    writer,
                    sheet_name="igor_command",
                    index=False,
                    header=True,
                )

        return output_path
