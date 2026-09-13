import sys
import types
from pathlib import Path

import pytest

ML = Path(__file__).resolve().parent.parent
if str(ML) not in sys.path:
    sys.path.insert(0, str(ML))

from training import phase17d_cicflowmeter_shim as shim


def upstream_create_sniffer(input_file, input_interface, output_mode, output,
                            input_directory=None, fields=None, verbose=False):
    assert sum([input_file is None, input_interface is None,
                input_directory is None]) == 2
    if fields is not None:
        fields = fields.split(",")
    return fields


class FakeSniffer:
    def __init__(self):
        self.started = False
        self.joined = 0

    def start(self):
        self.started = True

    def join(self):
        self.joined += 1

    def stop(self):
        pass


class FakeSession:
    def __init__(self):
        self.flushed = False

    def flush_flows(self):
        self.flushed = True


class TestUpstreamBugReproduction:

    def test_upstream_positional_call_crashes_on_bool_fields(self):
        args_fields = None
        args_verbose = False
        with pytest.raises(AttributeError):
            upstream_create_sniffer(
                "cap.pcap", None, "csv", "out.csv", args_fields, args_verbose)

    def test_upstream_positional_call_misroutes_verbose_into_fields(self):
        captured = {}

        def recorder(input_file, input_interface, output_mode, output,
                     input_directory=None, fields=None, verbose=False):
            captured["input_directory"] = input_directory
            captured["fields"] = fields
            captured["verbose"] = verbose

        recorder("cap.pcap", None, "csv", "out.csv", None, False)
        assert captured["fields"] is False
        assert captured["verbose"] is False


class TestShimFixesPlumbing:

    def _patch_backend(self, monkeypatch, recorder):
        sniffer, session = FakeSniffer(), FakeSession()

        def create_sniffer(**kwargs):
            recorder.update(kwargs)
            return sniffer, session

        monkeypatch.setattr(
            shim, "_load_backend",
            lambda: (create_sniffer, lambda *a, **k: None, lambda *a, **k: None))
        return sniffer, session

    def test_shim_passes_fields_none_and_verbose_false(self, monkeypatch):
        rec = {}
        sniffer, session = self._patch_backend(monkeypatch, rec)
        rc = shim.main(["-f", "cap.pcap", "-c", "out.csv"])
        assert rc == 0
        assert rec["input_file"] == "cap.pcap"
        assert rec["input_interface"] is None
        assert rec["output_mode"] == "csv"
        assert rec["output"] == "out.csv"
        assert rec["fields"] is None
        assert rec["verbose"] is False
        assert sniffer.started and session.flushed

    def test_shim_never_passes_bool_as_fields(self, monkeypatch):
        rec = {}
        self._patch_backend(monkeypatch, rec)
        shim.main(["-f", "cap.pcap", "-c", "out.csv", "-v"])
        assert rec["verbose"] is True
        assert rec["fields"] is None
        assert not isinstance(rec["fields"], bool)

    def test_shim_forwards_explicit_fields(self, monkeypatch):
        rec = {}
        self._patch_backend(monkeypatch, rec)
        shim.main(["-f", "cap.pcap", "-c", "out.csv", "--fields", "a,b,c"])
        assert rec["fields"] == "a,b,c"

    def test_shim_call_survives_real_upstream_fields_logic(self, monkeypatch):
        sniffer, session = FakeSniffer(), FakeSession()

        def create_sniffer(**kwargs):
            fields = kwargs["fields"]
            if fields is not None:
                fields = fields.split(",")
            return sniffer, session

        monkeypatch.setattr(
            shim, "_load_backend",
            lambda: (create_sniffer, lambda *a, **k: None, lambda *a, **k: None))
        assert shim.main(["-f", "cap.pcap", "-c", "out.csv"]) == 0


class TestShimCliContract:

    def test_frozen_invocation_parses(self):
        parser = shim.build_parser()
        args = parser.parse_args(["-f", "x.pcap", "-c", "y.csv"])
        assert args.input_file == "x.pcap"
        assert args.output_mode == "csv"
        assert args.output == "y.csv"
        assert args.fields is None
        assert args.verbose is False
        assert args.input_interface is None
        assert args.input_directory is None


from app.live import protocol as _protocol
from app.live import schema_guard as _schema_guard
from training import build_final_eval_dataset as _bfe


class TestFlowValidityContract:

    def test_status_from_validation_returns_dict_with_status_key(self):
        class _V:
            missing_features = []
            invalid_features = []
            unexpected_features = []
        status = _schema_guard.status_from_validation(_V(), None)
        assert isinstance(status, dict)
        assert "validation_status" in status

    def test_flow_is_valid_reads_the_status_key(self):
        assert _bfe.flow_is_valid({"validation_status": _protocol.STATUS_VALID}) is True
        assert _bfe.flow_is_valid(
            {"validation_status": _protocol.STATUS_NONFINITE_VALUE}) is False

    def test_raw_dict_never_equals_the_status_string(self):
        status = {"validation_status": _protocol.STATUS_VALID}
        assert status != _protocol.STATUS_VALID
        assert _bfe.flow_is_valid(status) is True
