import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "helpers" / "render.py"
SPEC = importlib.util.spec_from_file_location("video_use_render", MODULE_PATH)
assert SPEC and SPEC.loader
render = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render)


class ToneMapDetectionTests(unittest.TestCase):
    def _tonemap(self, frame: dict, stream: dict) -> str | None:
        def fake_run(cmd, **kwargs):
            show_entries = cmd[cmd.index("-show_entries") + 1]
            if show_entries.startswith("frame="):
                self.assertIn("0%+#1", cmd)
                payload = {"frames": [frame]} if frame else {"frames": []}
            else:
                payload = {"streams": [stream]}
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")

        with patch.object(render.subprocess, "run", side_effect=fake_run):
            return render.tonemap_filter(Path("source.mp4"))

    def test_tagged_hlg_is_tone_mapped_with_its_own_tags(self):
        tags = {"color_transfer": "arib-std-b67", "color_primaries": "bt2020",
                "color_space": "bt2020nc", "pix_fmt": "yuv420p10le"}
        chain = self._tonemap(tags, tags)
        self.assertTrue(chain.startswith(
            "setparams=color_trc=arib-std-b67:color_primaries=bt2020:colorspace=bt2020nc,"))
        self.assertTrue(chain.endswith(render.TONEMAP_CHAIN))

    def test_hlg_signalled_only_in_sei_is_read_from_the_decoded_frame(self):
        stream = {"color_transfer": "bt2020-10", "color_primaries": "bt2020",
                  "color_space": "bt2020nc", "pix_fmt": "yuv420p10le"}
        frame = dict(stream, color_transfer="arib-std-b67")
        self.assertIn("color_trc=arib-std-b67", self._tonemap(frame, stream))

    def test_transfer_only_fills_bt2020_primaries_and_matrix(self):
        tags = {"color_transfer": "smpte2084", "pix_fmt": "yuv420p10le"}
        chain = self._tonemap(tags, tags)
        self.assertIn("color_trc=smpte2084:color_primaries=bt2020:colorspace=bt2020nc", chain)

    def test_stream_tags_are_used_when_no_frame_decodes(self):
        stream = {"color_transfer": "arib-std-b67", "color_primaries": "bt2020",
                  "color_space": "bt2020nc", "pix_fmt": "yuv420p10le"}
        self.assertIsNotNone(self._tonemap({}, stream))

    def test_8bit_untagged_source_is_sdr(self):
        self.assertIsNone(self._tonemap({"pix_fmt": "yuv420p"}, {"pix_fmt": "yuv420p"}))

    def test_10bit_rec709_source_is_sdr(self):
        tags = {"color_transfer": "bt709", "color_primaries": "bt709",
                "color_space": "bt709", "pix_fmt": "yuv422p10le"}
        self.assertIsNone(self._tonemap(tags, tags))

    def test_untagged_10bit_source_stops_instead_of_guessing(self):
        tags = {"color_transfer": "unknown", "pix_fmt": "yuv420p10le"}
        with self.assertRaises(SystemExit) as stop:
            self._tonemap(tags, tags)
        self.assertIn("transfer_characteristics", str(stop.exception))

    def test_bt2020_source_without_transfer_stops(self):
        tags = {"color_primaries": "bt2020", "color_space": "bt2020nc", "pix_fmt": "yuv420p"}
        with self.assertRaises(SystemExit):
            self._tonemap(tags, tags)

    def test_failed_probe_is_treated_as_sdr(self):
        def failing_run(cmd, **kwargs):
            raise subprocess.CalledProcessError(1, cmd)

        with patch.object(render.subprocess, "run", side_effect=failing_run):
            self.assertIsNone(render.tonemap_filter(Path("source.mp4")))


if __name__ == "__main__":
    unittest.main()
