from pathlib import Path
import os


# Code lives in the git workspace. Data/output live in OneDrive by default.
CODE_ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_ROOT = Path(r"C:\Users\sgw02\OneDrive\python\new_strategy")
DEFAULT_STOCK_ROOT = Path(r"C:\Users\sgw02\OneDrive\python\Stock")
DEFAULT_STRATEGY_OUTPUT_SUBDIR = "strategy_v2"
DEFAULT_TREND_DATA_SUBDIR = "trend_lab"
DEFAULT_TREND_OUTPUT_SUBDIR = "trend_lab"


def data_root() -> Path:
    # Root for strategy data, outputs, logs, and caches.
    return Path(os.getenv("NEW_STRATEGY_DATA_ROOT", str(DEFAULT_DATA_ROOT))).expanduser()


def output_root() -> Path:
    # Output files are separated under the data root by default.
    return Path(os.getenv("NEW_STRATEGY_OUTPUT_ROOT", str(data_root() / "output"))).expanduser()


def cache_root() -> Path:
    # Cache files are separated under the data root by default.
    return Path(os.getenv("NEW_STRATEGY_CACHE_ROOT", str(data_root() / "cache"))).expanduser()


def stock_root() -> Path:
    # Raw yearly stock Excel files live outside the code repo.
    return Path(os.getenv("NEW_STRATEGY_STOCK_ROOT", str(DEFAULT_STOCK_ROOT))).expanduser()


def data_path(*parts: str) -> Path:
    return data_root().joinpath(*parts)


def output_path(*parts: str) -> Path:
    return output_root().joinpath(*parts)


def strategy_output_subdir() -> str:
    value = str(os.getenv("NEW_STRATEGY_OUTPUT_SUBDIR_NAME", DEFAULT_STRATEGY_OUTPUT_SUBDIR)).strip()
    return value or DEFAULT_STRATEGY_OUTPUT_SUBDIR


def strategy_output_path(*parts: str) -> Path:
    return output_path(strategy_output_subdir(), *parts)


def trend_data_subdir() -> str:
    value = str(os.getenv("NEW_STRATEGY_TREND_DATA_SUBDIR_NAME", DEFAULT_TREND_DATA_SUBDIR)).strip()
    return value or DEFAULT_TREND_DATA_SUBDIR


def trend_output_subdir() -> str:
    value = str(os.getenv("NEW_STRATEGY_TREND_OUTPUT_SUBDIR_NAME", DEFAULT_TREND_OUTPUT_SUBDIR)).strip()
    return value or DEFAULT_TREND_OUTPUT_SUBDIR


def trend_data_path(*parts: str) -> Path:
    # Dedicated data area for trend-lab only. Keep it isolated from core strategy runtime files.
    return data_path(trend_data_subdir(), *parts)


def trend_output_path(*parts: str) -> Path:
    # Dedicated output area for trend-lab only. Keep it isolated from strategy_v2 core contracts.
    return strategy_output_path(trend_output_subdir(), *parts)


def cache_path(*parts: str) -> Path:
    return cache_root().joinpath(*parts)


def stock_path(*parts: str) -> Path:
    return stock_root().joinpath(*parts)

