from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys

from mcrdp.profiles import normalize_header


@dataclass(frozen=True)
class VariableDefinition:
    key: str
    display_name: str
    aliases: tuple[str, ...]
    igor_label: str
    unit: str
    show_in_ui: bool
    selection_keys: tuple[str, ...]


@dataclass(frozen=True)
class PresetDefinition:
    log10_keys: tuple[str, ...]
    linear_keys: tuple[str, ...]
    mean_key: str | None
    recursive: bool


@dataclass(frozen=True)
class NamingSettings:
    order: str = "var-num-name"
    separator: str = "_"
    number_digits: int = 3
    number_start: int = 0
    replacements: tuple[tuple[str, str], ...] = (
        (".", "r"),
        ("/", "per"),
        ("%", "percent"),
    )
    strip_trailing_number: bool = True


@dataclass(frozen=True)
class ExportSettings:
    default_output_name: str = "sorted.xlsx"
    include_original: bool = True
    include_name_map: bool = True
    include_igor_command: bool = True
    conflict_policy: str = "ask"
    auto_export: bool = False


@dataclass(frozen=True)
class IgorSettings:
    default_axis: str = "L"
    remember_selection: bool = True



def _external_app_root() -> Path | None:
    """Return the directory containing the .app bundle when frozen on macOS."""
    if not getattr(sys, "frozen", False):
        return None

    executable = Path(sys.executable).resolve()
    for parent in executable.parents:
        if parent.suffix.lower() == ".app":
            return parent.parent
    return executable.parent


def variable_config_candidates(explicit_path: str | Path | None = None) -> list[Path]:
    """Return editable and bundled variable-config locations in priority order."""
    candidates: list[Path] = []

    if explicit_path is not None:
        candidates.append(Path(explicit_path).expanduser())

    app_root = _external_app_root()
    if app_root is not None:
        candidates.append(app_root / "config" / "variables.json")

    # Source-tree execution: project_root/config/variables.json.
    module_path = Path(__file__).resolve()
    if len(module_path.parents) >= 3:
        candidates.append(module_path.parents[2] / "config" / "variables.json")

    # PyInstaller --add-data fallback inside the application bundle.
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / "config" / "variables.json")

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve(strict=False)
        if resolved not in seen:
            unique.append(resolved)
            seen.add(resolved)
    return unique


def resolve_variable_config(explicit_path: str | Path | None = None) -> Path:
    candidates = variable_config_candidates(explicit_path)
    for path in candidates:
        if path.is_file():
            return path

    checked = "\n".join(f"  - {path}" for path in candidates)
    raise FileNotFoundError(
        "variables.json was not found. Checked:\n" + checked
    )


class VariableCatalog:
    """Validated variable aliases, UI selections, presets, and IGOR labels."""

    def __init__(self, config_path: str | Path | None = None):
        self.config_path = resolve_variable_config(config_path)
        self.variables: dict[str, VariableDefinition] = {}
        self.alias_to_key: dict[str, str] = {}
        self.presets_by_key: dict[str, PresetDefinition] = {}
        self.schema_version = 1
        self.naming = NamingSettings()
        self.export = ExportSettings()
        self.igor = IgorSettings()
        self._load()

    def _load(self) -> None:
        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON in {self.config_path}: line {exc.lineno}, "
                f"column {exc.colno}: {exc.msg}"
            ) from exc

        schema_version = raw.get("schema_version")
        if schema_version not in (1, 2):
            raise ValueError(
                f"Unsupported schema_version in {self.config_path}; expected 1 or 2."
            )
        self.schema_version = int(schema_version)

        items = raw.get("variables")
        if not isinstance(items, list) or not items:
            raise ValueError("variables.json must contain a non-empty 'variables' list.")

        variables: dict[str, VariableDefinition] = {}
        alias_to_key: dict[str, str] = {}

        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"variables[{index}] must be an object.")

            key = str(item.get("key", "")).strip()
            display_name = str(item.get("display_name", "")).strip()
            aliases_raw = item.get("aliases", [])

            if not key:
                raise ValueError(f"variables[{index}].key is empty.")
            if key.startswith("log_"):
                raise ValueError(f"Variable key must not start with 'log_': {key}")
            if key in variables:
                raise ValueError(f"Duplicate variable key: {key}")
            if not display_name:
                raise ValueError(f"display_name is empty for variable: {key}")
            if not isinstance(aliases_raw, list) or not aliases_raw:
                raise ValueError(f"aliases must be a non-empty list for variable: {key}")

            aliases: list[str] = []
            seen_local: set[str] = set()
            for alias_value in [display_name, *aliases_raw]:
                alias = str(alias_value).strip()
                normalized = normalize_header(alias)
                if not normalized or normalized in seen_local:
                    continue
                existing = alias_to_key.get(normalized)
                if existing is not None and existing != key:
                    raise ValueError(
                        f"Alias is assigned to both '{existing}' and '{key}': {alias}"
                    )
                aliases.append(alias)
                seen_local.add(normalized)
                alias_to_key[normalized] = key

            selection_raw = item.get("selection_keys", [key])
            if not isinstance(selection_raw, list) or not selection_raw:
                raise ValueError(f"selection_keys must be a non-empty list for: {key}")
            selection_keys = tuple(str(v).strip() for v in selection_raw if str(v).strip())

            variables[key] = VariableDefinition(
                key=key,
                display_name=display_name,
                aliases=tuple(aliases),
                igor_label=str(item.get("igor_label", key)),
                unit=str(item.get("unit", "")),
                show_in_ui=bool(item.get("show_in_ui", True)),
                selection_keys=selection_keys,
            )

        for definition in variables.values():
            unknown = [key for key in definition.selection_keys if key not in variables]
            if unknown:
                raise ValueError(
                    f"Unknown selection_keys for '{definition.key}': {unknown}"
                )

        presets = raw.get("presets", {})
        if not isinstance(presets, dict):
            raise ValueError("'presets' must be an object.")

        presets_by_key: dict[str, PresetDefinition] = {}
        for preset_name, preset_raw in presets.items():
            if isinstance(preset_raw, list):
                log10_raw = preset_raw
                linear_raw = []
                mean_raw = None
                recursive = False
            elif isinstance(preset_raw, dict):
                log10_raw = preset_raw.get("log10", [])
                linear_raw = preset_raw.get("linear", [])
                mean_raw = preset_raw.get("mean_variable")
                recursive = bool(preset_raw.get("recursive", False))
            else:
                raise ValueError(f"Preset '{preset_name}' must be a list or object.")

            if not isinstance(log10_raw, list) or not isinstance(linear_raw, list):
                raise ValueError(
                    f"Preset '{preset_name}' log10 and linear values must be lists."
                )
            log10_keys = tuple(str(v).strip() for v in log10_raw if str(v).strip())
            linear_keys = tuple(str(v).strip() for v in linear_raw if str(v).strip())
            mean_key = None if mean_raw in (None, "") else str(mean_raw).strip()
            selected_keys = [*log10_keys, *linear_keys]
            if mean_key:
                selected_keys.append(mean_key)
            unknown = [key for key in selected_keys if key not in variables]
            if unknown:
                raise ValueError(f"Preset '{preset_name}' has unknown keys: {unknown}")
            presets_by_key[str(preset_name)] = PresetDefinition(
                log10_keys=log10_keys,
                linear_keys=linear_keys,
                mean_key=mean_key,
                recursive=recursive,
            )

        naming_raw = raw.get("naming", {})
        if not isinstance(naming_raw, dict):
            raise ValueError("'naming' must be an object.")
        order = str(naming_raw.get("order", "var-num-name"))
        valid_orders = {
            "var-num-name", "var-name-num", "num-var-name",
            "num-name-var", "name-var-num", "name-num-var",
        }
        if order not in valid_orders:
            raise ValueError(f"Unsupported column-name order: {order}")
        separator = str(naming_raw.get("separator", "_"))
        if not separator:
            raise ValueError("naming.separator must not be empty.")
        number_digits = int(naming_raw.get("number_digits", 3))
        number_start = int(naming_raw.get("number_start", 0))
        if not 1 <= number_digits <= 9:
            raise ValueError("naming.number_digits must be between 1 and 9.")
        if number_start < 0:
            raise ValueError("naming.number_start must be zero or greater.")
        replacements_raw = naming_raw.get(
            "replacements", {".": "r", "/": "per", "%": "percent"}
        )
        if not isinstance(replacements_raw, dict):
            raise ValueError("naming.replacements must be an object.")
        replacements = tuple(
            (str(source), str(replacement))
            for source, replacement in replacements_raw.items()
            if str(source)
        )

        export_raw = raw.get("export", {})
        if not isinstance(export_raw, dict):
            raise ValueError("'export' must be an object.")
        conflict_policy = str(export_raw.get("conflict_policy", "ask"))
        if conflict_policy not in {"ask", "overwrite", "auto_number"}:
            raise ValueError(
                "export.conflict_policy must be ask, overwrite, or auto_number."
            )
        default_output_name = str(
            export_raw.get("default_output_name", "sorted.xlsx")
        ).strip()
        if not default_output_name:
            raise ValueError("export.default_output_name must not be empty.")

        igor_raw = raw.get("igor", {})
        if not isinstance(igor_raw, dict):
            raise ValueError("'igor' must be an object.")
        default_axis = str(igor_raw.get("default_axis", "L"))
        if default_axis not in {"L", "R"}:
            raise ValueError("igor.default_axis must be L or R.")

        self.variables = variables
        self.alias_to_key = alias_to_key
        self.presets_by_key = presets_by_key
        self.naming = NamingSettings(
            order=order,
            separator=separator,
            number_digits=number_digits,
            number_start=number_start,
            replacements=replacements,
            strip_trailing_number=bool(
                naming_raw.get("strip_trailing_number", True)
            ),
        )
        self.export = ExportSettings(
            default_output_name=default_output_name,
            include_original=bool(export_raw.get("include_original", True)),
            include_name_map=bool(export_raw.get("include_name_map", True)),
            include_igor_command=bool(
                export_raw.get("include_igor_command", True)
            ),
            conflict_policy=conflict_policy,
            auto_export=bool(export_raw.get("auto_export", False)),
        )
        self.igor = IgorSettings(
            default_axis=default_axis,
            remember_selection=bool(igor_raw.get("remember_selection", True)),
        )

    def key_from_header(self, value: object) -> str | None:
        exact = str(value).strip()
        if exact in self.variables:
            return exact
        return self.alias_to_key.get(normalize_header(value))

    def selection_keys(self, value: str) -> tuple[str, ...]:
        # Exact keys remain case-sensitive; this is required for T and t.
        if value in self.variables:
            return self.variables[value].selection_keys

        key = self.alias_to_key.get(normalize_header(value))
        if key is None:
            return ()
        return self.variables[key].selection_keys

    def visible_display_names(self) -> list[str]:
        return [
            definition.display_name
            for definition in self.variables.values()
            if definition.show_in_ui
        ]

    def _display_name_for_key(self, key: str) -> str:
        definition = self.variables[key]
        if definition.show_in_ui:
            return definition.display_name

        for candidate in self.variables.values():
            if candidate.show_in_ui and key in candidate.selection_keys:
                return candidate.display_name
        return definition.display_name

    def canonical_display_name(self, value: str) -> str | None:
        if value in self.variables:
            return self._display_name_for_key(value)
        key = self.alias_to_key.get(normalize_header(value))
        if key is None:
            return None
        return self._display_name_for_key(key)

    def quick_selects(self) -> dict[str, list[str]]:
        return {
            preset_name: list(dict.fromkeys(
                self._display_name_for_key(key)
                for key in (*preset.log10_keys, *preset.linear_keys)
            ))
            for preset_name, preset in self.presets_by_key.items()
        }

    def preset_profiles(self) -> dict[str, dict[str, object]]:
        profiles: dict[str, dict[str, object]] = {}
        for preset_name, preset in self.presets_by_key.items():
            profiles[preset_name] = {
                "log10": list(dict.fromkeys(
                    self._display_name_for_key(key) for key in preset.log10_keys
                )),
                "linear": list(dict.fromkeys(
                    self._display_name_for_key(key) for key in preset.linear_keys
                )),
                "mean_variable": (
                    self._display_name_for_key(preset.mean_key)
                    if preset.mean_key else None
                ),
                "recursive": preset.recursive,
            }
        return profiles

    def label_info(self, key: str) -> tuple[str, str]:
        definition = self.variables.get(key)
        if definition is None:
            return key, ""
        return definition.igor_label, definition.unit

