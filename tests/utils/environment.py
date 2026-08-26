from pathlib import Path


def load_env_value(env_file: Path, name: str) -> str:
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ValueError(f"Arquivo de ambiente nao encontrado: {env_file}") from exc

    for original in lines:
        line = original.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if value:
            return value
        break

    raise ValueError(f"Variavel obrigatoria ausente em {env_file}: {name}")


def load_env_path(env_file: Path, name: str, base_dir: Path) -> Path:
    path = Path(load_env_value(env_file, name)).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()
