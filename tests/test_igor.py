from pathlib import Path

from mcrdp.igor import IgorCommandBuilder
from mcrdp.variables import VariableCatalog


CONFIG_PATH = Path(__file__).parents[1] / "config" / "variables.json"


def test_igor_command_uses_catalog_labels():
    builder = IgorCommandBuilder(VariableCatalog(CONFIG_PATH))
    command = builder.build_command(
        data_name_set=[{"w": "w_000_A", "G1": "G1_000_A"}],
        x_data_name="w",
        list_y_data_name=["G1"],
    )
    assert "AppendToGraph G1_000_A vs w_000_A" in command
    assert "Label bottom" in command
    assert "Label left" in command
