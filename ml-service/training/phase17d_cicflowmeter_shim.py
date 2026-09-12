import argparse
import sys


def _load_backend():
    from cicflowmeter.sniffer import (
        create_sniffer,
        process_directory,
        process_directory_merged,
    )
    return create_sniffer, process_directory, process_directory_merged


def build_parser():
    parser = argparse.ArgumentParser()

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("-i", "--interface", action="store",
                             dest="input_interface")
    input_group.add_argument("-f", "--file", action="store", dest="input_file")
    input_group.add_argument("-d", "--directory", action="store",
                             dest="input_directory")

    output_group = parser.add_mutually_exclusive_group(required=True)
    output_group.add_argument("-c", "--csv", action="store_const", const="csv",
                              dest="output_mode")
    output_group.add_argument("-u", "--url", action="store_const", const="url",
                              dest="output_mode")

    parser.add_argument("output")
    parser.add_argument("--fields", action="store", dest="fields")
    parser.add_argument("--merge", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    create_sniffer, process_directory, process_directory_merged = _load_backend()

    if args.merge and not args.input_directory:
        parser.error("--merge can only be used with -d/--directory mode")

    if args.input_directory:
        if args.merge:
            process_directory_merged(args.input_directory, args.output,
                                     args.fields, args.verbose)
        else:
            process_directory(args.input_directory, args.output,
                              args.fields, args.verbose)
        return 0

    sniffer, session = create_sniffer(
        input_file=args.input_file,
        input_interface=args.input_interface,
        output_mode=args.output_mode,
        output=args.output,
        fields=args.fields,
        verbose=args.verbose,
    )
    sniffer.start()
    try:
        sniffer.join()
    except KeyboardInterrupt:
        sniffer.stop()
    finally:
        if hasattr(session, "_gc_stop"):
            session._gc_stop.set()
            session._gc_thread.join(timeout=2.0)
        sniffer.join()
        session.flush_flows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
