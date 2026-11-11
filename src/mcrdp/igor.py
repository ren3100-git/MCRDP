from __future__ import annotations

from mcrdp.variables import VariableCatalog


class IgorCommandBuilder:
    def __init__(self, catalog: VariableCatalog | None = None):
        self.catalog = catalog or VariableCatalog()

    def get_processed_keys(self, data_name_set: list[dict[str, str]]) -> list[str]:
        keys = set()
        for data_names in data_name_set:
            keys.update(data_names.keys())
        return sorted(keys)

    def build_command(
        self,
        data_name_set: list[dict[str, str]],
        x_data_name: str,
        list_y_data_name: list[str],
        LR: str = "L",
    ) -> str:
        def find_label_info(key: str):
            if key.startswith("log_"):
                key_base = key.removeprefix("log_")
                var, unit = self.catalog.label_info(key_base)
                style = "log"
            else:
                var, unit = self.catalog.label_info(key)
                style = "lin"
            return style, var, unit

        def make_label(list_key: list[str]) -> str:
            styles, vars_, units = map(list, zip(*(find_label_info(key) for key in list_key)))

            if len(set(styles)) != 1:
                raise ValueError("対数/線型が一致していません")
            if len(set(units)) != 1:
                raise ValueError("単位が一致していません")

            var_text = "\\f00,".join(sorted(set(vars_)))
            unit_text = "" if "" in units else "\\f00 / " + list(set(units))[0]

            if list(set(styles))[0] == "log":
                return '"log(\\f00' + var_text + unit_text + '\\f00)"'
            return '"' + var_text + unit_text + '"'

        y_styles = {find_label_info(key)[0] for key in list_y_data_name}
        if len(y_styles) != 1:
            raise ValueError("対数/線型が一致していません")
        y_style = next(iter(y_styles))

        b_label_command = "Label bottom " + make_label([x_data_name])

        base_format = (
            'ModifyGraph log=0,tick=2,standoff=0,mirror(bottom)=1,nticks=5,'
            'fSize=20,axThick=1.5,font="Arial",mode=3,marker=8,msize=5,'
            'mrkThick=2,opaque=1,lblMargin=15'
        )

        if LR == "L":
            appending_command = "AppendToGraph"
            displaying_command = "Display;\n"
            v_label_command = "Label left " + make_label(list_y_data_name)

            axis_parts = ['mirror(left)=1']
            if y_style == "log":
                axis_parts.extend([
                    'manTick(left)={0,1,0,0}',
                    'manMinor(left)={0,0}',
                ])

        elif LR == "R":
            appending_command = "AppendToGraph/R"
            displaying_command = ""
            v_label_command = "Label right " + make_label(list_y_data_name)

            axis_parts = []
            if y_style == "log":
                axis_parts.extend([
                    'manTick(right)={0,1,0,0}',
                    'manMinor(right)={0,0}',
                ])

        else:
            raise ValueError("LR must be 'L' or 'R'.")

        formatting_command = base_format
        if axis_parts:
            formatting_command += "," + ",".join(axis_parts)
        formatting_command += ";DelayUpdate"

        chunks: list[str] = []
        current = displaying_command

        for data_names in data_name_set:
            for y_data_name in list_y_data_name:
                if x_data_name in data_names and y_data_name in data_names:
                    x_ = data_names[x_data_name].replace(".", "_").replace("/", "_")
                    y_ = data_names[y_data_name].replace(".", "_").replace("/", "_")
                    current += f" {appending_command} {y_} vs {x_};"
                    if len(current) >= 2000:
                        chunks.append(current)
                        current = ""

        if current:
            chunks.append(current)

        return "\n".join(chunks + [formatting_command, b_label_command, v_label_command])
