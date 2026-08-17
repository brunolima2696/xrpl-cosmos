import shutil
import tempfile
from pathlib import Path

from yui_common import (
    YUI_HOME,
    chain_template,
    cli_main,
    run_yui,
    selected_chains_from_cli,
    write_json,
    yui_config,
)


def main():
    chains = selected_chains_from_cli(
        "Registra no YUI as chains selecionadas."
    )
    configured = {
        chain["chain-id"] for chain in yui_config().get("chains", [])
    }
    missing = [chain for chain in chains if chain["chain_id"] not in configured]
    if not missing:
        print("Todas as chains já estão registradas; etapa ignorada.")
        return

    staging_dir = Path(tempfile.mkdtemp(prefix=".setup-chains-", dir=YUI_HOME))
    try:
        for chain in missing:
            write_json(
                staging_dir / f"{chain['name']}.json",
                chain_template(chain),
            )
        container_dir = f"/root/.yui-relayer/{staging_dir.name}"
        run_yui("chains", "add-dir", container_dir)
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


if __name__ == "__main__":
    cli_main(main)
