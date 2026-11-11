from pathlib import Path
import json

import pandas as pd

from mcrdp.models import NAME_MAP_COLUMNS, NAME_TABLE_COLUMNS, ProcessorConfig
from mcrdp.processor import RheoDataProcessor
from mcrdp.profiles import SOFTWARE_PROFILES
from mcrdp.variables import VariableCatalog
from mcrdp.excel import ExcelExporter


CONFIG_PATH = Path(__file__).parents[1] / "config" / "variables.json"


def test_parser_fallback_preserves_blank_lines_and_values(tmp_path, monkeypatch):
    path = tmp_path / "rheoplus.csv"
    path.write_text(
        '名前:,,,試料\n'
        ',Angular Frequency,Storage Modulus\n'
        '\n'
        '1,1,"1,000"\n'
        '2,10,2000\n',
        encoding="cp932",
    )
    original_read_csv = pd.read_csv
    engines = []

    def failing_c_parser(*args, **kwargs):
        engines.append(kwargs.get("engine", "c"))
        if engines[-1] == "c":
            raise pd.errors.ParserError(
                "Error tokenizing data. C error: Buffer overflow caught"
            )
        return original_read_csv(*args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", failing_c_parser)
    processor = RheoDataProcessor(CONFIG_PATH)
    candidate = processor._read_candidate(
        path, "RheoPlus", SOFTWARE_PROFILES["RheoPlus"], "cp932"
    )
    assert engines == ["c", "python"]
    assert processor.find_data_range(candidate.df_raw) == [(3, 4)]
    assert processor._pick_variables(candidate.df_raw, 1) == [(1, "w"), (2, "G1")]
    assert candidate.df_raw.iloc[0, 3] == "試料"
    assert candidate.df_raw.iloc[3, 2] == "1000"


def _rheoplus_frame(sample_name: str) -> pd.DataFrame:
    rows = [
        ["Name:", "", "", sample_name, ""],
        ["", "Angular Frequency", "Storage Modulus", "Loss Modulus", "Temperature"],
        ["", "", "", "", ""],
        [1, 1.0, 10.0, 5.0, 25.0],
        [2, 10.0, 20.0, 8.0, 25.0],
        ["", "", "", "", ""],
    ]
    return pd.DataFrame(rows)


def test_multiple_processed_frames_have_unique_column_index(tmp_path, monkeypatch):
    processor = RheoDataProcessor(CONFIG_PATH)
    paths = [tmp_path / "a.csv", tmp_path / "b.csv"]
    for path in paths:
        path.write_text("placeholder", encoding="utf-8")

    frames = {
        paths[0]: _rheoplus_frame("sampleA"),
        paths[1]: _rheoplus_frame("sampleB"),
    }
    profile = SOFTWARE_PROFILES["RheoPlus"]

    monkeypatch.setattr(processor, "collect_files", lambda *_args, **_kwargs: paths)

    def fake_detect(path):
        from mcrdp.models import DetectedInput
        return DetectedInput(
            software="RheoPlus",
            profile=profile,
            encoding="utf-8",
            df_raw=frames[Path(path)],
            score=100,
        )

    monkeypatch.setattr(processor, "detect_input_file", fake_detect)

    result = processor.load_and_process_directory(
        tmp_path,
        config=ProcessorConfig(
            linear_vars=["角周波数", "貯蔵弾性率", "損失弾性率"],
            mean_variable="温度",
        ),
    )

    assert result.variables.columns.is_unique
    assert len(result.processed_files) == 2
    assert result.mean_variable == "温度"
    exported = processor.variables_with_export_headers(result)
    assert exported.columns.is_unique
    assert exported.iloc[0].tolist() == [25.0] * exported.shape[1]


def test_mean_header_table_definition_is_display_only():
    assert NAME_TABLE_COLUMNS == [
        "export",
        "n_points",
        "variable_key",
        "mean_header",
        "internal_name",
        "output_name",
    ]
    assert "mean_header" not in NAME_MAP_COLUMNS


def test_mean_header_uses_the_selected_source_column(tmp_path, monkeypatch):
    processor = RheoDataProcessor(CONFIG_PATH)
    path = tmp_path / "a.csv"
    path.write_text("placeholder", encoding="utf-8")
    frame = _rheoplus_frame("sampleA")
    profile = SOFTWARE_PROFILES["RheoPlus"]

    monkeypatch.setattr(processor, "collect_files", lambda *_args, **_kwargs: [path])

    def fake_detect(_path):
        from mcrdp.models import DetectedInput
        return DetectedInput(
            software="RheoPlus",
            profile=profile,
            encoding="utf-8",
            df_raw=frame,
            score=100,
        )

    monkeypatch.setattr(processor, "detect_input_file", fake_detect)

    result = processor.load_and_process_directory(
        tmp_path,
        config=ProcessorConfig(
            linear_vars=["貯蔵弾性率"],
            mean_variable="角周波数",
        ),
    )

    exported = processor.variables_with_export_headers(result)
    assert exported.iloc[0].tolist() == [5.5]
    assert result.mean_variable == "角周波数"


def test_excluding_middle_column_keeps_headers_and_data_aligned():
    from mcrdp.models import ProcessResult

    processor = RheoDataProcessor(CONFIG_PATH)
    result = ProcessResult(
        original=pd.DataFrame(),
        variables=pd.DataFrame([
            ["w_000_A", "G1_000_A", "G2_000_A"],
            [1.0, 10.0, 5.0],
            [10.0, 20.0, 8.0],
        ]),
        data_name_set=[],
        processed_files=[],
        name_map=pd.DataFrame([
            [True, 2, "w", "w_000_A", "w_out"],
            [False, 2, "G1", "G1_000_A", "G1_out"],
            [True, 2, "G2", "G2_000_A", "G2_out"],
        ], columns=NAME_MAP_COLUMNS),
        column_info=pd.DataFrame([
            ["w_000_A", "w", 25.0],
            ["G1_000_A", "G1", 25.0],
            ["G2_000_A", "G2", 25.0],
        ], columns=["internal_name", "header_variable", "mean_value"]),
    )

    exported = processor.variables_with_export_headers(result)

    assert exported.shape == (5, 2)
    assert exported.iloc[0].tolist() == [25.0, 25.0]
    assert exported.iloc[1].tolist() == ["w", "G2"]
    assert exported.iloc[2].tolist() == ["w_out", "G2_out"]
    assert exported.iloc[3].tolist() == [1.0, 5.0]
    assert exported.iloc[4].tolist() == [10.0, 8.0]


def test_v2_naming_and_processing_preset_settings(tmp_path):
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    raw["naming"].update({
        "separator": "-",
        "number_digits": 4,
        "number_start": 12,
        "replacements": {"/": "_per_"},
        "strip_trailing_number": False,
    })
    raw["presets"]["Custom"] = {
        "log10": ["G1"],
        "linear": ["T"],
        "mean_variable": "T",
        "recursive": True,
    }
    path = tmp_path / "variables.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    processor = RheoDataProcessor(path)

    assert processor.make_column_name("G1", 12, "sample", "var-num-name") == (
        "G1-0012-sample"
    )
    assert processor.sanitize("A/B_12") == "A_per_B_12"
    assert processor.preset_profiles["Custom"] == {
        "log10": ["貯蔵弾性率"],
        "linear": ["温度"],
        "mean_variable": "温度",
        "recursive": True,
    }


def test_v1_variable_config_is_migrated_in_memory(tmp_path):
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    raw["schema_version"] = 1
    raw["presets"] = {
        name: profile["log10"]
        for name, profile in raw["presets"].items()
    }
    raw.pop("naming")
    raw.pop("export")
    raw.pop("igor")
    path = tmp_path / "variables-v1.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    catalog = VariableCatalog(path)

    assert catalog.schema_version == 1
    assert catalog.naming.separator == "_"
    assert catalog.export.include_original is True
    assert catalog.preset_profiles()["Frequency sweep (SAOS)"]["log10"] == [
        "角周波数",
        "貯蔵弾性率",
        "損失弾性率",
    ]


def test_excel_optional_sheets_can_be_disabled(tmp_path):
    from mcrdp.models import ProcessResult

    processor = RheoDataProcessor(CONFIG_PATH)
    result = ProcessResult(
        original=pd.DataFrame([["original"]]),
        variables=pd.DataFrame([["G1_000_A"], [10.0]]),
        data_name_set=[],
        processed_files=[],
        name_map=pd.DataFrame([
            [True, 1, "G1", "G1_000_A", "G1_out"],
        ], columns=NAME_MAP_COLUMNS),
        column_info=pd.DataFrame([
            ["G1_000_A", "G1", ""],
        ], columns=["internal_name", "header_variable", "mean_value"]),
    )
    output_path = tmp_path / "minimal.xlsx"

    ExcelExporter(processor).export(
        result,
        output_path,
        include_original=False,
        include_name_map=False,
        include_igor_command=False,
    )

    assert pd.ExcelFile(output_path).sheet_names == ["variables"]
