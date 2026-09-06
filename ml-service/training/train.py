import argparse
import sys
from pathlib import Path

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from training.pipeline import config as config_module
from training.pipeline import runner
from training.pipeline.artifacts import ArtifactError
from training.pipeline.balancing import BalancingError
from training.pipeline.data import DEFAULT_MIN_CLASS_ROWS, DatasetError
from training.pipeline.splitting import SplitError

DEFAULT_CONFIG_DIR = "training/configs"


def _apply_overrides(config, args):
    if args.seed is not None:
        config.seed = args.seed
    if args.artifact_name:
        config.output["artifact_name"] = args.artifact_name
    if args.reports_dir:
        config.output["reports_dir"] = args.reports_dir
    if args.models_dir:
        config.output["models_dir"] = args.models_dir
    if args.name:
        config.name = args.name
    return config


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pipeline i riprodhueshem i trajnimit per CICIDS2017.")
    parser.add_argument("config", help=f"Path drejt nje YAML-i (p.sh. {DEFAULT_CONFIG_DIR}/...)")
    parser.add_argument("--sample-rows", type=int, default=None,
                        help="Trajno mbi nje nen-mostre te stratifikuar (smoke test). "
                             "Regjistrohet ne raport si dataset.subsampled=true.")
    parser.add_argument("--min-class-rows", type=int, default=None,
                        help="Rreshta minimale per klase kur perdoret --sample-rows "
                             "(default: 10), qe klasat e rralla t'i mbijetojne split-it")
    parser.add_argument("--seed", type=int, default=None,
                        help="Mbishkruaj seed-in e konfigurimit")
    parser.add_argument("--name", default=None, help="Mbishkruaj emrin e xhirimit")
    parser.add_argument("--artifact-name", default=None,
                        help="Mbishkruaj output.artifact_name")
    parser.add_argument("--models-dir", default=None, help="Mbishkruaj output.models_dir")
    parser.add_argument("--reports-dir", default=None, help="Mbishkruaj output.reports_dir")
    parser.add_argument("--force", action="store_true",
                        help="Lejo mbishkrimin e artefakteve ekzistuese")
    parser.add_argument("--no-save", action="store_true",
                        help="Vlereso pa ruajtur artefakte (dry run)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    try:
        config = _apply_overrides(config_module.load(args.config), args)
        result = runner.run(
            config,
            sample_rows=args.sample_rows,
            min_class_rows=(args.min_class_rows
                            if args.min_class_rows is not None
                            else DEFAULT_MIN_CLASS_ROWS),
            force=args.force,
            save=not args.no_save,
            verbose=not args.quiet,
        )
    except (config_module.ConfigError, DatasetError, SplitError, BalancingError,
            ArtifactError, ValueError) as error:
        print(f"\nGABIM: {error}", file=sys.stderr)
        return 1

    if args.no_save:
        print("\n--no-save: asnje artefakt s'u shkrua.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
