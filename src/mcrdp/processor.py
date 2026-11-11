from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from mcrdp.models import (
    COLUMN_INFO_COLUMNS,
    NAME_MAP_COLUMNS,
    DetectedInput,
    FileReport,
    ProcessResult,
    ProcessorConfig,
)
from mcrdp.naming import make_column_name, sanitize_sample_name
from mcrdp.profiles import (
    SAMPLE_NAME_FLAGS,
    SOFTWARE_PROFILES,
    SoftwareProfile,
    normalize_header,
)
from mcrdp.variables import VariableCatalog


class RheoDataProcessor:
    def __init__(self, variable_config_path: str | Path | None = None):
        self.catalog = VariableCatalog(variable_config_path)
        self.quick_selects = self.catalog.quick_selects()
        self.preset_profiles = self.catalog.preset_profiles()

    def get_clean_variable_list(self) -> list[str]:
        return self.catalog.visible_display_names()

    def normalize_selection_names(self, values: Iterable[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            display_name = self.catalog.canonical_display_name(str(value))
            if display_name is not None and display_name not in seen:
                normalized.append(display_name)
                seen.add(display_name)
        return normalized

    def make_column_name(
        self,
        variable_key: str,
        number: int,
        sample_name: str,
        name_order: str,
    ) -> str:
        return make_column_name(
            variable_key,
            number,
            sample_name,
            name_order,
            separator=self.catalog.naming.separator,
            number_digits=self.catalog.naming.number_digits,
        )

    def sanitize(self, name: str) -> str:
        return sanitize_sample_name(
            name,
            replacements=self.catalog.naming.replacements,
            strip_trailing_number=self.catalog.naming.strip_trailing_number,
        )

    def _expanded_selected_vars(self, config: ProcessorConfig) -> tuple[set[str], set[str]]:
        def expand(values: Iterable[str]) -> set[str]:
            keys: set[str] = set()
            unknown: list[str] = []
            for value in values:
                selected = self.catalog.selection_keys(str(value))
                if not selected:
                    unknown.append(str(value))
                keys.update(selected)
            if unknown:
                raise ValueError(f"Unknown variable selection(s): {unknown}")
            return keys

        log10_vars = expand(config.log10_vars)
        linear_vars = expand(config.linear_vars)
        return log10_vars, linear_vars

    def _expanded_mean_vars(self, config: ProcessorConfig) -> tuple[str, ...]:
        if not config.mean_variable:
            return ()

        keys = self.catalog.selection_keys(str(config.mean_variable))
        if not keys:
            raise ValueError(f"Unknown mean variable: {config.mean_variable}")
        return keys

    def _mean_value_for_block(
        self,
        df_num: pd.DataFrame,
        start: int,
        end: int,
        variables: list[tuple[int, str]],
        mean_variable_keys: tuple[str, ...],
    ) -> object:
        if not mean_variable_keys:
            return ""

        variable_columns = {key: col_idx for col_idx, key in variables}
        for key in mean_variable_keys:
            col_idx = variable_columns.get(key)
            if col_idx is None:
                continue
            raw = df_num.iloc[start:end + 1, col_idx]
            if raw.notna().any():
                return float(raw.mean())
        return ""

    def find_data_range(
        self,
        df: pd.DataFrame,
        datapoints_col: int = 0,
        first_datapoint: int = 1,
    ) -> list[tuple[int, int]]:
        if datapoints_col >= df.shape[1]:
            return []

        col = df.iloc[:, datapoints_col].copy()
        points = pd.to_numeric(col, errors="coerce").to_numpy(dtype=float)

        starts = [
            i for i, v in enumerate(points)
            if not np.isnan(v) and v == first_datapoint
        ]

        numeric_to_nan_ends = [
            i
            for i in range(len(points) - 1)
            if not np.isnan(points[i]) and np.isnan(points[i + 1])
        ]
        if len(points) > 0 and not np.isnan(points[-1]):
            numeric_to_nan_ends.append(len(points) - 1)

        ranges: list[tuple[int, int]] = []
        for idx, start in enumerate(starts):
            next_start = starts[idx + 1] if idx + 1 < len(starts) else len(points)

            candidate_ends = [e for e in numeric_to_nan_ends if start <= e < next_start]
            if candidate_ends:
                end = candidate_ends[0]
            else:
                valid_numeric_rel = np.where(~np.isnan(points[start:next_start]))[0]
                if len(valid_numeric_rel) == 0:
                    continue
                end = start + int(valid_numeric_rel[-1])

            if start <= end:
                ranges.append((start, end))

        return ranges

    def finder(
        self,
        df: pd.DataFrame,
        object_flag: Iterable[str],
        object_col: int = 3,
        finding_col: int = 0,
    ) -> list[list[object]]:
        if finding_col >= df.shape[1] or object_col >= df.shape[1]:
            return []
        col = df.iloc[:, finding_col].tolist()
        flags = {normalize_header(flag) for flag in object_flag}
        return [
            [i, str(df.iloc[i, object_col])]
            for i, val in enumerate(col)
            if normalize_header(val) in flags
        ]

    def _pick_variables(self, df_raw: pd.DataFrame, var_row: int) -> list[tuple[int, str]]:
        if var_row < 0 or var_row >= len(df_raw):
            return []
        variables: list[tuple[int, str]] = []
        for col_idx, v in enumerate(df_raw.iloc[var_row, :]):
            if v == "":
                continue
            key = self.catalog.key_from_header(v)
            if key is not None:
                variables.append((col_idx, key))
        return variables

    def _get_sample_names(
        self,
        df_raw: pd.DataFrame,
        profile: SoftwareProfile,
    ) -> list[list[object]]:
        names = [
            [i, str(val).replace(" ", "_")]
            for i, val in self.finder(
                df_raw,
                SAMPLE_NAME_FLAGS,
                object_col=profile.name_col,
                finding_col=profile.find_col,
            )
            if str(val).strip()
        ]
        return names if names else [[-1, "noname"]]

    def _read_candidate(
        self,
        path: Path,
        software: str,
        profile: SoftwareProfile,
        encoding: str,
    ) -> DetectedInput:
        read_options = dict(
            encoding=encoding,
            sep=profile.sep,
            header=None,
            names=range(100),
            skip_blank_lines=False,
        )
        try:
            df_raw = pd.read_csv(path, **read_options)
        except pd.errors.ParserError:
            # Some instrument exports exceed the C tokenizer's buffer limits.
            # Retry without dropping rows: header offsets depend on blank lines.
            df_raw = pd.read_csv(path, engine="python", **read_options)
        df_raw = df_raw.fillna("").replace(",", "", regex=True)
        nonempty_columns = (df_raw != "").any(axis=0).to_numpy()
        if nonempty_columns.any():
            last_column = int(np.flatnonzero(nonempty_columns)[-1])
            df_raw = df_raw.iloc[:, :last_column + 1].copy()

        data_ranges = self.find_data_range(
            df_raw,
            datapoints_col=profile.datapoints_col,
            first_datapoint=profile.first_point,
        )
        if not data_ranges:
            raise ValueError("no numeric data block was found")

        recognized_counts: list[int] = []
        total_points = 0
        for start, end in data_ranges:
            variables = self._pick_variables(df_raw, start - profile.space_var)
            if variables:
                recognized_counts.append(len(variables))
                total_points += end - start + 1

        if not recognized_counts:
            raise ValueError("no configured variable header was found")

        # Metadata labels such as Test:/Point No./Interval data: are not part
        # of this score. A candidate must have both numeric blocks and known
        # variable headers at the profile-specific relative row position.
        score = max(recognized_counts) * 1000 + len(recognized_counts) * 10
        score += min(total_points, 9)
        return DetectedInput(
            software=software,
            profile=profile,
            encoding=encoding,
            df_raw=df_raw,
            score=score,
        )

    def detect_input_file(self, path: str | Path) -> DetectedInput:
        path = Path(path)
        candidates: list[DetectedInput] = []
        errors: list[str] = []

        for software, profile in SOFTWARE_PROFILES.items():
            best_for_profile: DetectedInput | None = None
            attempted_encodings: set[str] = set()
            for encoding in profile.encodings:
                normalized_encoding = encoding.lower().replace("_", "-")
                if normalized_encoding in attempted_encodings:
                    continue
                attempted_encodings.add(normalized_encoding)
                try:
                    candidate = self._read_candidate(path, software, profile, encoding)
                except Exception as exc:
                    errors.append(f"{software}/{encoding}: {exc}")
                    continue
                if best_for_profile is None or candidate.score > best_for_profile.score:
                    best_for_profile = candidate

            if best_for_profile is not None:
                candidates.append(best_for_profile)

        if not candidates:
            detail = "; ".join(errors[:6])
            if len(errors) > 6:
                detail += "; ..."
            raise ValueError(f"unsupported or unreadable rheometer file ({detail})")

        candidates.sort(key=lambda item: item.score, reverse=True)
        if len(candidates) > 1 and candidates[0].score == candidates[1].score:
            names = ", ".join(candidate.software for candidate in candidates[:2])
            raise ValueError(f"software detection is ambiguous: {names}")
        return candidates[0]

    def _make_name_map_row(
        self,
        variable_key: str,
        internal_name: str,
        n_points: int,
    ) -> dict[str, object]:
        # internal_name is the processing-safe name.
        # output_name is editable later, and export controls variables-sheet output.
        # n_points is the number of numeric datapoints in this exported column.
        return {
            "export": True,
            "n_points": int(n_points),
            "variable_key": variable_key,
            "internal_name": internal_name,
            "output_name": internal_name,
        }

    def _build_block_columns(
        self,
        df_num: pd.DataFrame,
        start: int,
        end: int,
        variables: list[tuple[int, str]],
        number: int,
        sample_name: str,
        config: ProcessorConfig,
        log10_vars: set[str],
        linear_vars: set[str],
        mean_value: object,
    ) -> tuple[
        list[list[object]],
        dict[str, str],
        list[dict[str, object]],
        list[dict[str, object]],
    ]:
        data_name_dict: dict[str, str] = {}
        block_columns: list[list[object]] = []
        name_map_rows: list[dict[str, object]] = []
        column_info_rows: list[dict[str, object]] = []
        selected_vars = log10_vars | linear_vars

        # Keep the output order by data block.
        # Example: T,w,G1,G2,T,w,G1,G2,... rather than T,T,...,w,w,...
        for varcol, key in variables:
            if key not in selected_vars:
                continue

            raw = df_num.iloc[start:end + 1, varcol]

            # Do not export intervals where the selected variable has no numeric datapoints.
            if key in linear_vars and raw.notna().any():
                col_name = self.make_column_name(
                    key,
                    number,
                    sample_name,
                    config.name_order,
                )

                data_name_dict[key] = col_name
                block_columns.append([col_name] + raw.tolist())
                name_map_rows.append(
                    self._make_name_map_row(key, col_name, int(raw.notna().sum()))
                )
                column_info_rows.append({
                    "internal_name": col_name,
                    "header_variable": key,
                    "mean_value": mean_value,
                })

            if key in log10_vars:
                raw_log = np.log10(raw.where(raw > 0))
                if raw_log.notna().any():
                    log_key = f"log_{key}"
                    col_name = self.make_column_name(
                        log_key,
                        number,
                        sample_name,
                        config.name_order,
                    )

                    data_name_dict[log_key] = col_name
                    block_columns.append([col_name] + raw_log.tolist())
                    name_map_rows.append(
                        self._make_name_map_row(
                            log_key,
                            col_name,
                            int(raw_log.notna().sum()),
                        )
                    )
                    column_info_rows.append({
                        "internal_name": col_name,
                        "header_variable": key,
                        "mean_value": mean_value,
                    })

        return block_columns, data_name_dict, name_map_rows, column_info_rows

    def process_single_file(
        self,
        df_raw: pd.DataFrame,
        df_num: pd.DataFrame,
        profile: SoftwareProfile,
        config: ProcessorConfig,
        start_id: int = 0,
    ) -> tuple[
        pd.DataFrame,
        list[dict[str, str]],
        list[dict[str, object]],
        list[dict[str, object]],
        int,
    ]:
        data_ranges = self.find_data_range(
            df_raw,
            datapoints_col=profile.datapoints_col,
            first_datapoint=profile.first_point,
        )
        if not data_ranges:
            return pd.DataFrame(), [], [], [], start_id

        names = self._get_sample_names(df_raw, profile)

        log10_vars, linear_vars = self._expanded_selected_vars(config)
        mean_variable_keys = self._expanded_mean_vars(config)

        output_columns: list[list[object]] = []
        data_name_set: list[dict[str, str]] = []
        name_map_rows_all: list[dict[str, object]] = []
        column_info_rows_all: list[dict[str, object]] = []
        name_idx = 0
        current_id = start_id

        for start, end in data_ranges:
            variables = self._pick_variables(df_raw, start - profile.space_var)
            if not variables:
                continue

            while name_idx + 1 < len(names) and start > names[name_idx + 1][0]:
                name_idx += 1

            dataname = names[name_idx][1]
            clean_dataname = self.sanitize(dataname)

            mean_value = self._mean_value_for_block(
                df_num=df_num,
                start=start,
                end=end,
                variables=variables,
                mean_variable_keys=mean_variable_keys,
            )

            (
                block_columns,
                data_name_dict,
                name_map_rows,
                column_info_rows,
            ) = self._build_block_columns(
                df_num=df_num,
                start=start,
                end=end,
                variables=variables,
                number=current_id,
                sample_name=clean_dataname,
                config=config,
                log10_vars=log10_vars,
                linear_vars=linear_vars,
                mean_value=mean_value,
            )

            # Skip empty intervals entirely so they do not create blank columns or IGOR command entries.
            if not data_name_dict:
                continue

            output_columns.extend(block_columns)
            data_name_set.append(data_name_dict)
            name_map_rows_all.extend(name_map_rows)
            column_info_rows_all.extend(column_info_rows)
            current_id += 1

        processed_df = pd.DataFrame(output_columns).T if output_columns else pd.DataFrame()
        return (
            processed_df,
            data_name_set,
            name_map_rows_all,
            column_info_rows_all,
            current_id,
        )

    def collect_files(
        self,
        input_dir: str | Path,
        recursive: bool = False,
    ) -> list[Path]:
        input_dir = Path(input_dir)
        if not input_dir.exists():
            raise FileNotFoundError(f"Input directory not found: {input_dir}")

        patterns = ["*.csv", "*.CSV", "*.txt", "*.TXT", "*.tsv", "*.TSV"]

        files: list[Path] = []
        for pat in patterns:
            files.extend(sorted(input_dir.rglob(pat) if recursive else input_dir.glob(pat)))
        return sorted(set(files))

    def load_and_process_directory(
        self,
        input_dir: str | Path,
        recursive: bool = False,
        config: ProcessorConfig | None = None,
    ) -> ProcessResult:
        config = config or ProcessorConfig()

        if not config.log10_vars and not config.linear_vars:
            raise ValueError("variable undefined")

        # Validate selections before attempting any input files.
        self._expanded_selected_vars(config)

        file_list = self.collect_files(input_dir, recursive=recursive)
        if not file_list:
            raise FileNotFoundError("No input files found.")

        original_df_list: list[pd.DataFrame] = []
        converted_col_list: list[pd.DataFrame] = []
        data_name_set: list[dict[str, str]] = []
        name_map_rows_all: list[dict[str, object]] = []
        column_info_rows_all: list[dict[str, object]] = []
        processed_files: list[Path] = []
        file_reports: list[FileReport] = []
        current_id = self.catalog.naming.number_start

        for path in file_list:
            try:
                detected = self.detect_input_file(path)
            except Exception as exc:
                file_reports.append(FileReport(
                    path=path,
                    software="Unknown",
                    encoding="",
                    status="skipped",
                    message=str(exc),
                ))
                continue

            df_raw = detected.df_raw
            df_num = df_raw.apply(lambda x: pd.to_numeric(x, errors="coerce"))

            original_df_list.append(df_raw)

            (
                processed_df,
                file_data_names,
                file_name_map_rows,
                file_column_info_rows,
                current_id,
            ) = self.process_single_file(
                df_raw=df_raw,
                df_num=df_num,
                profile=detected.profile,
                config=config,
                start_id=current_id,
            )
            if not processed_df.empty:
                converted_col_list.append(processed_df)
                data_name_set.extend(file_data_names)
                name_map_rows_all.extend(file_name_map_rows)
                column_info_rows_all.extend(file_column_info_rows)
                processed_files.append(path)
                file_reports.append(FileReport(
                    path=path,
                    software=detected.software,
                    encoding=detected.encoding,
                    status="processed",
                ))
            else:
                file_reports.append(FileReport(
                    path=path,
                    software=detected.software,
                    encoding=detected.encoding,
                    status="no_selected_data",
                    message="No numeric data were found for the selected variables.",
                ))

        if not original_df_list:
            details = "\n".join(
                f"- {report.path.name}: {report.message}"
                for report in file_reports[:10]
            )
            raise RuntimeError(
                "No supported RheoPlus/RheoCompass files were detected."
                + (f"\n{details}" if details else "")
            )

        df_original_all = pd.concat(original_df_list, ignore_index=True)
        df_converted_all = (
            pd.concat(converted_col_list, axis=1, ignore_index=True)
            if converted_col_list
            else pd.DataFrame()
        )
        name_map_source = pd.DataFrame(name_map_rows_all, columns=NAME_MAP_COLUMNS)
        name_map = self._order_name_map_by_variables(df_converted_all, name_map_source)
        column_info_source = pd.DataFrame(
            column_info_rows_all,
            columns=["internal_name", "header_variable", "mean_value"],
        )
        column_info = self._order_column_info_by_variables(
            df_converted_all,
            column_info_source,
        )

        return ProcessResult(
            original=df_original_all,
            variables=df_converted_all,
            data_name_set=data_name_set,
            processed_files=processed_files,
            mean_variable=config.mean_variable,
            name_map=name_map,
            column_info=column_info,
            file_reports=file_reports,
        )

    def _order_name_map_by_variables(
        self,
        variables: pd.DataFrame,
        name_map_source: pd.DataFrame,
    ) -> pd.DataFrame:
        if variables.empty or name_map_source.empty:
            return pd.DataFrame(columns=NAME_MAP_COLUMNS)

        source = name_map_source.drop_duplicates(subset=["internal_name"], keep="first")
        lookup = {
            str(row["internal_name"]): row
            for _, row in source.iterrows()
        }

        ordered_rows: list[dict[str, object]] = []
        for internal_name in variables.iloc[0, :].tolist():
            key = str(internal_name)
            row = lookup.get(key)
            if row is None:
                continue
            ordered_rows.append({
                "export": bool(row.get("export", True)),
                "n_points": int(row.get("n_points", 0)),
                "variable_key": str(row["variable_key"]),
                "internal_name": str(row["internal_name"]),
                "output_name": str(row["output_name"]),
            })

        return pd.DataFrame(ordered_rows, columns=NAME_MAP_COLUMNS)

    def _order_column_info_by_variables(
        self,
        variables: pd.DataFrame,
        column_info_source: pd.DataFrame,
    ) -> pd.DataFrame:
        columns = ["internal_name", "header_variable", "mean_value"]
        if variables.empty or column_info_source.empty:
            return pd.DataFrame(columns=columns)

        source = column_info_source.drop_duplicates(
            subset=["internal_name"],
            keep="first",
        )
        lookup = {
            str(row["internal_name"]): row
            for _, row in source.iterrows()
        }

        ordered_rows: list[dict[str, object]] = []
        for internal_name in variables.iloc[0, :].tolist():
            key = str(internal_name)
            row = lookup.get(key)
            if row is None:
                continue
            ordered_rows.append({
                "internal_name": key,
                "header_variable": str(row["header_variable"]),
                "mean_value": row["mean_value"],
            })

        return pd.DataFrame(ordered_rows, columns=columns)

    def validate_output_names(self, name_map: pd.DataFrame) -> None:
        if name_map.empty:
            return

        missing = [col for col in NAME_MAP_COLUMNS if col not in name_map.columns]
        if missing:
            raise ValueError(f"name_map is missing column(s): {missing}")

        active = name_map[name_map["export"].astype(bool)].copy()
        if active.empty:
            raise ValueError("No columns are selected for variables output.")

        output_names = active["output_name"].astype(str).str.strip().tolist()
        empty_rows = [idx + 1 for idx, name in enumerate(output_names) if not name]
        if empty_rows:
            raise ValueError(f"output_name is empty in exported row(s): {empty_rows}")

        duplicated = sorted({name for name in output_names if output_names.count(name) > 1})
        if duplicated:
            joined = ", ".join(duplicated[:10])
            if len(duplicated) > 10:
                joined += ", ..."
            raise ValueError(f"output_name is duplicated among exported columns: {joined}")
    def set_output_name_map(self, result: ProcessResult, name_map: pd.DataFrame) -> None:
        self.validate_output_names(name_map)
        result.name_map = name_map[NAME_MAP_COLUMNS].copy()
        result.name_map["export"] = result.name_map["export"].astype(bool)
        result.name_map["n_points"] = pd.to_numeric(
            result.name_map["n_points"],
            errors="coerce",
        ).fillna(0).astype(int)
    def _output_name_mapping(self, result: ProcessResult) -> dict[str, str]:
        if result.name_map.empty:
            return {}
        self.validate_output_names(result.name_map)
        active = result.name_map[result.name_map["export"].astype(bool)]
        return dict(
            zip(
                active["internal_name"].astype(str),
                active["output_name"].astype(str),
            )
        )
    def apply_existing_name_map_edits(
        self,
        result: ProcessResult,
        previous_name_map: pd.DataFrame | None,
    ) -> None:
        if previous_name_map is None or previous_name_map.empty or result.name_map.empty:
            return

        previous = previous_name_map.drop_duplicates(subset=["internal_name"], keep="first")
        previous_lookup = {
            str(row["internal_name"]): row
            for _, row in previous.iterrows()
        }

        updated = result.name_map.copy()
        for idx, row in updated.iterrows():
            internal_name = str(row["internal_name"])
            old = previous_lookup.get(internal_name)
            if old is None:
                continue
            updated.at[idx, "output_name"] = str(old.get("output_name", row["output_name"]))
            updated.at[idx, "export"] = bool(old.get("export", row.get("export", True)))

        result.name_map = updated[NAME_MAP_COLUMNS].copy()
        result.name_map["export"] = result.name_map["export"].astype(bool)

    def variables_with_output_names(self, result: ProcessResult) -> pd.DataFrame:
        df = result.variables.copy()
        if df.empty:
            return df

        mapping = self._output_name_mapping(result)
        if not mapping:
            return df.iloc[:, []]

        internal_names = [str(v) for v in df.iloc[0, :].tolist()]
        keep_indices = [idx for idx, name in enumerate(internal_names) if name in mapping]
        df = df.iloc[:, keep_indices].copy()
        df.iloc[0, :] = [mapping[str(v)] for v in df.iloc[0, :].tolist()]
        return df

    def variables_with_export_headers(self, result: ProcessResult) -> pd.DataFrame:
        df = result.variables.copy()
        if df.empty:
            return df

        mapping = self._output_name_mapping(result)
        if not mapping:
            return df.iloc[:, []]

        internal_names = [str(v) for v in df.iloc[0, :].tolist()]
        keep_indices = [idx for idx, name in enumerate(internal_names) if name in mapping]
        kept_internal_names = [internal_names[idx] for idx in keep_indices]
        # Filtering keeps the original column labels (for example 0, 2 after
        # excluding column 1). Reset both axes before stacking the new header
        # rows, otherwise pandas aligns by those old labels and shifts data.
        data_rows = df.iloc[1:, keep_indices].reset_index(drop=True)
        data_rows.columns = range(len(keep_indices))

        info_lookup = {}
        if not result.column_info.empty:
            info_lookup = {
                str(row["internal_name"]): row
                for _, row in result.column_info.iterrows()
            }

        mean_row = []
        variable_row = []
        output_name_row = []
        for internal_name in kept_internal_names:
            info = info_lookup.get(internal_name)
            mean_row.append("" if info is None else info.get("mean_value", ""))
            variable_row.append(
                "" if info is None else str(info.get("header_variable", ""))
            )
            output_name_row.append(mapping[internal_name])

        header_rows = pd.DataFrame([mean_row, variable_row, output_name_row])
        return pd.concat([header_rows, data_rows], ignore_index=True)

    def make_output_data_name_set(self, result: ProcessResult) -> list[dict[str, str]]:
        mapping = self._output_name_mapping(result)
        converted: list[dict[str, str]] = []
        for data_names in result.data_name_set:
            converted.append({
                key: mapping[str(internal_name)]
                for key, internal_name in data_names.items()
                if str(internal_name) in mapping
            })
        return converted
