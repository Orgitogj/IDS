import numpy as np
import pandas as pd
from pathlib import Path

CICIDS2017_FILES = [
    "Monday-WorkingHours.pcap_ISCX.csv",
    "Tuesday-WorkingHours.pcap_ISCX.csv",
    "Wednesday-workingHours.pcap_ISCX.csv",
    "Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv",
    "Thursday-WorkingHours-Afternoon-Infilteration.pcap_ISCX.csv",
    "Friday-WorkingHours-Morning.pcap_ISCX.csv",
    "Friday-WorkingHours-Afternoon-PortScan.pcap_ISCX.csv",
    "Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv",
]

IDENTIFIER_COLUMNS = ["Flow ID", "Source IP", "Source Port", "Destination IP", "Timestamp"]


def load_single_file(filepath: Path) -> pd.DataFrame:
    df = pd.read_csv(filepath, encoding="latin1", low_memory=False)
    df.columns = df.columns.str.strip()

    if "Fwd Header Length.1" in df.columns:
        df = df.drop(columns=["Fwd Header Length.1"])

    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=["Flow Bytes/s", "Flow Packets/s"])

    df["source_file"] = filepath.name

    return df


def load_all_cicids2017(dataset_dir: str) -> pd.DataFrame:
    base_path = Path(dataset_dir)
    frames = []

    for filename in CICIDS2017_FILES:
        filepath = base_path / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Mungon file: {filepath}")

        df = load_single_file(filepath)
        frames.append(df)
        print(f"  {filename}: {len(df):,} rreshta (pas pastrimit)")

    combined = pd.concat(frames, ignore_index=True)
    return combined