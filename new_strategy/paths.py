from pathlib import Path
import os


CODE_ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_ROOT = Path(r"C:\Users\sgw02\OneDrive\python\new_strategy")


def data_root() -> Path:
    return Path(os.getenv("NEW_STRATEGY_DATA_ROOT", str(DEFAULT_DATA_ROOT))).expanduser()


def output_root() -> Path:
    return Path(os.getenv("NEW_STRATEGY_OUTPUT_ROOT", str(data_root() / "output"))).expanduser()


def cache_root() -> Path:
    return Path(os.getenv("NEW_STRATEGY_CACHE_ROOT", str(data_root() / "cache"))).expanduser()


def data_path(*parts: str) -> Path:
    return data_root().joinpath(*parts)


def output_path(*parts: str) -> Path:
    return output_root().joinpath(*parts)


def cache_path(*parts: str) -> Path:
    return cache_root().joinpath(*parts)

