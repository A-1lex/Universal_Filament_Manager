"""Trust-boundary checks for selected-plate sliced-3MF intake."""
import hashlib
import io
import stat
import struct
import unittest
import warnings
import zipfile
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from ufm.integrations.sliced_files import (
    SlicedFileRejected,
    inspect_3mf_bytes,
    inspect_3mf_file,
)

FIXTURES = Path(__file__).resolve().parents[2] / "linked-stack/haspelsync/test/fixtures"
FILAMENT = '<filament id="1" used_g="0.0005" color="#FFFFFF" type="PLA"/>'


def plate_xml(index: int = 1, filament: str = FILAMENT, extra: str = "") -> str:
    return f'<plate><metadata key="index" value="{index}"/>{filament}{extra}</plate>'


def archive(xml: str | bytes | None = None, extras: tuple[tuple[str, bytes], ...] = (),
            compression: int = zipfile.ZIP_STORED) -> bytes:
    buffer = io.BytesIO()
    with warnings.catch_warnings(), zipfile.ZipFile(buffer, "w", compression=compression) as z:
        warnings.simplefilter("ignore", UserWarning)
        z.writestr("Metadata/slice_info.config", xml or f"<config>{plate_xml()}</config>")
        z.writestr("Metadata/plate_1.gcode", b"G90\nM83\nG1 E1\n")
        for name, content in extras:
            z.writestr(name, content)
    return buffer.getvalue()


def inspect(data: bytes, plate: int = 1):  # type: ignore[no-untyped-def]
    return inspect_3mf_bytes(data, plate=plate, expected_sha256=hashlib.sha256(data).hexdigest())


class SlicedFileTests(unittest.TestCase):
    def test_directory_limit_before_zipfile_allocation(self) -> None:
        data = bytearray(archive())
        end = data.rfind(b"PK\x05\x06")
        struct.pack_into("<HH", data, end + 8, 2049, 2049)
        with patch("ufm.integrations.sliced_files.zipfile.ZipFile") as reader:
            with self.assertRaises(SlicedFileRejected):
                inspect(bytes(data))
            reader.assert_not_called()

    def test_unused_empty_layer_list_does_not_inflate_coverage(self) -> None:
        xml = '<config>' + plate_xml(extra='<layer_filament_lists>'
            '<layer_filament_list filament_list="" layer_ranges="999999 999999"/>'
            '</layer_filament_lists>') + '</config>'
        facts = inspect(archive(xml))
        self.assertEqual(facts.layer_filaments, ())
        self.assertEqual(facts.filaments[0].mass_mg, 1)

    def test_half_mg_rounding_unknowns_and_same_colour_identity(self) -> None:
        xml = '<config>' + plate_xml(filament=FILAMENT +
            '<filament id="6" used_g="0" used_m="0" color="#FFFFFF" type="PLA"/>') + '</config>'
        result = inspect(archive(xml))
        self.assertEqual([(f.logical_material, f.mass_mg) for f in result.filaments], [(0, 1), (5, 0)])
        self.assertIsNone(result.filaments[0].used_m)
        self.assertEqual(result.filaments[1].used_m, Decimal(0))
        self.assertIsNone(result.includes_purge)
        self.assertIn("ROUND_HALF_UP", result.filaments[0].mass_provenance)
        with self.assertRaises(FrozenInstanceError):
            result.plate = 2

    def test_selected_plate_opaque_gcode_and_hashes(self) -> None:
        xml = '<config>' + plate_xml() + plate_xml(2, FILAMENT.replace('0.0005', '2.5')) + '</config>'
        data = archive(xml, (("Metadata/plate_2.gcode", b"opaque G-code"),))
        facts = inspect(data, 2)
        self.assertEqual(facts.filaments[0].mass_mg, 2500)
        self.assertEqual(facts.gcode_bytes, b"opaque G-code")
        self.assertEqual(facts.gcode_sha256, hashlib.sha256(b"opaque G-code").hexdigest())
        self.assertEqual(facts.file_sha256, hashlib.sha256(data).hexdigest())
        self.assertNotIn('value="1"', facts.normalized_xml)
        self.assertEqual(facts.quantity, "estimate")

    def test_fixture_metadata_and_real_synthetic_fixture_archive(self) -> None:
        for path in FIXTURES.glob("*.config"):
            with self.subTest(fixture=path.name):
                self.assertTrue(inspect(archive(path.read_bytes())).filaments)
        path = FIXTURES / "p2s_two_colours.gcode.3mf"
        result = inspect_3mf_file(path, plate=1, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(len(result.filaments), 2)

    def test_layer_ranges_and_sparse_ids(self) -> None:
        facts = inspect(archive((FIXTURES / "split_layer_ranges.config").read_bytes()))
        self.assertEqual(facts.layer_filaments[0].layer_ranges, ((0, 13), (86, 127)))
        self.assertEqual([f.logical_material for f in facts.filaments], [0, 1, 3])
        for value in ('1 0', '0 1000001', '0 2,2 3', '-1 5', '0', '0 nope'):
            extra = '<layer_filament_lists><layer_filament_list filament_list="0" layer_ranges="' + value + '"/></layer_filament_lists>'
            with self.subTest(value=value), self.assertRaises(SlicedFileRejected):
                inspect(archive('<config>' + plate_xml(extra=extra) + '</config>'))

    def test_strict_numbers_do_not_become_zero(self) -> None:
        for value in ('NaN', 'Infinity', '-1', '1e2', '1,2', ' 0', '', '1000000.001', 'nope'):
            for key in ('used_g', 'used_m'):
                filament = f'<filament id="1" used_g="0" {key}="{value}"/>' if key == 'used_m' else f'<filament id="1" used_g="{value}"/>'
                with self.subTest(key=key, value=value), self.assertRaises(SlicedFileRejected):
                    inspect(archive('<config>' + plate_xml(filament=filament) + '</config>'))
        with self.assertRaises(SlicedFileRejected):
            inspect(archive('<config>' + plate_xml(filament='<filament id="1"/>') + '</config>'))

    def test_missing_hash_or_plate_and_mismatches(self) -> None:
        data = archive()
        for plate in (0, -1, True, 2):
            with self.subTest(plate=plate), self.assertRaises(SlicedFileRejected):
                inspect(data, plate)
        for digest in ('0' * 64, '', 'A' * 64):
            with self.subTest(digest=digest), self.assertRaises(SlicedFileRejected):
                inspect_3mf_bytes(data, plate=1, expected_sha256=digest)
        with self.assertRaises(TypeError):
            inspect_3mf_bytes(data, plate=1)  # type: ignore[call-arg]
        xml = '<config>' + plate_xml(2) + '</config>'
        with self.assertRaises(SlicedFileRejected):
            inspect(archive(xml))

    def test_duplicate_plate_filament_and_metadata_identity(self) -> None:
        for xml in ('<config>' + plate_xml() * 2 + '</config>',
                    '<config>' + plate_xml(filament=FILAMENT * 2) + '</config>',
                    '<config>' + plate_xml(extra='<metadata key="index" value="1"/>') + '</config>'):
            with self.subTest(xml=xml), self.assertRaises(SlicedFileRejected):
                inspect(archive(xml))

    def test_unsafe_and_duplicate_zip_paths(self) -> None:
        for name in ('../secret', '/absolute', 'C:/secret', 'a/../b', 'a//b',
                     'Metadata/SLICE_INFO.CONFIG'):
            with self.subTest(name=name), self.assertRaises(SlicedFileRejected):
                inspect(archive(extras=((name, b"private-marker"),)))
        with self.assertRaises(SlicedFileRejected):
            inspect(archive(extras=(("a/b", b"x"),)).replace(b"a/b", b"a\\b"))
        for names in (("same", "same"), ("caf\u00e9", "cafe\u0301")):
            with self.subTest(names=names), self.assertRaises(SlicedFileRejected):
                inspect(archive(extras=tuple((n, b"x") for n in names)))

    def test_xml_attack_malformed_and_resource_bounds(self) -> None:
        for xml in ('<!DOCTYPE config [<!ENTITY x "private-marker">]><config/>',
                    '<?xml version="1.0" encoding="ISO-8859-1"?><config/>',
                    '<config>', '<config>' + '<x>' * 20 + '</x>' * 20 + '</config>',
                    '<config>' + '<x/>' * 8200 + '</config>', b'\xff<config/>'):
            with self.subTest(xml=str(xml)[:30]), self.assertRaises(SlicedFileRejected) as caught:
                inspect(archive(xml))
            self.assertNotIn("private-marker", str(caught.exception))
        with self.assertRaises(SlicedFileRejected):
            inspect(b"not a ZIP private-marker")

    def test_zip_compression_symlink_ratio_and_crc(self) -> None:
        with self.assertRaises(SlicedFileRejected):
            inspect(archive(compression=zipfile.ZIP_BZIP2))
        with self.assertRaises(SlicedFileRejected):
            inspect(archive(extras=(("bomb", b"0" * 100000),), compression=zipfile.ZIP_DEFLATED))
        stream = io.BytesIO(archive())
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(stream, "a") as z:
            z.writestr(info, b"target")
        with self.assertRaises(SlicedFileRejected):
            inspect(stream.getvalue())
        data = bytearray(archive())
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            entry = z.getinfo("Metadata/plate_1.gcode")
            offset = entry.header_offset
            lengths = struct.unpack_from('<HH', data, offset + 26)
            data[offset + 30 + sum(lengths)] ^= 1
        with self.assertRaises(SlicedFileRejected):
            inspect(bytes(data))

    def test_encrypted_and_declared_size_headers_are_rejected(self) -> None:
        original = archive()
        for field_offset, field_format, value in ((8, '<H', 1), (24, '<I', 600 * 1024 * 1024)):
            data = bytearray(original)
            central = data.index(b'PK\x01\x02')
            struct.pack_into(field_format, data, central + field_offset, value)
            with self.subTest(field=field_offset), self.assertRaises(SlicedFileRejected):
                inspect(bytes(data))
        bad_mass = '<filament id="1" used_g="10000.001"/>'
        with self.assertRaises(SlicedFileRejected):
            inspect(archive('<config>' + plate_xml(filament=bad_mass) + '</config>'))

    def test_caps_apply_before_large_reads(self) -> None:
        for key, limit in (("MAX_ARCHIVE_BYTES", 10), ("MAX_ENTRIES", 1),
                           ("MAX_DECLARED_BYTES", 1), ("MAX_METADATA_BYTES", 10),
                           ("MAX_GCODE_BYTES", 1)):
            with self.subTest(key=key), patch('ufm.integrations.sliced_files.' + key, limit):
                with self.assertRaises(SlicedFileRejected):
                    inspect(archive())
        fake = io.BytesIO(b"x" * 101)
        with patch('ufm.integrations.sliced_files.MAX_ARCHIVE_BYTES', 100), patch.object(Path, 'open', return_value=fake):
            with self.assertRaises(SlicedFileRejected):
                inspect_3mf_file('ignored', plate=1, expected_sha256='0' * 64)
