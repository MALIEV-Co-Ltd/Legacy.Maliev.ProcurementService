"""Require the declared Thai and English fixture literals as strict UTF-8."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementMasterQuerySourceTests.cs"


def verify(raw):
    text = raw.decode("utf-8", errors="strict")
    supplier = "\u0e0a\u0e34\u0e49\u0e19\u0e07\u0e32\u0e19"
    order = "\u0e43\u0e1a\u0e2a\u0e31\u0e48\u0e07\u0e0b\u0e37\u0e49\u0e2d"
    snippets = (
        f'[InlineData("{supplier}", 4567)]',
        f'Name = "part1234{supplier}"',
        f'[InlineData("{order}", 999)]',
        f'Notes = "Probe001203{order}"',
        '[InlineData("PART1234", null)]',
        '[InlineData("PROBE", 999)]',
    )
    if raw.startswith(b"\xef\xbb\xbf") or "\ufffd" in text or any(snippet not in text for snippet in snippets):
        raise ValueError("Fixture text differs from its declared UTF-8 Thai/English codepoints")
    return {"encoding": "UTF-8", "exactLiteralChecks": len(snippets)}


if __name__ == "__main__":
    print(verify(SOURCE.read_bytes()))
