"""Reviewed current artifact transport consumer; frozen source and native grants stay unchanged."""
import hashlib
import stat

WORKFLOW = 'Legacy.Maliev.ProcurementService.Tests/Workflows/WorkflowContractTests.cs'
PREVIOUS_BLOB = '133875aa827a87ebcfdc775a63d2702fb3846c4d'
CURRENT_BLOB = '69dd38abb2b72f8b295ce1a160a68a47a2dbc89d'
PREVIOUS_SHA256 = '1fcc17194f91991d573eaecd2f372aad56346737e16fcae07792d63c0b0bfddd'
CURRENT_SHA256 = '8ff79ccc9e5c516d493b3295cf1dfaaf5a2ddf5156cfc452e289b9a9ccf0adfd'
PREVIOUS_BYTES = 52974
CURRENT_BYTES = 54436
INVERSE_EDITS = ((1815, 2391, b'    private static void BuildAndTest_RejectsPreviousUploadArtifactPins()\n    {\n        foreach (var previousPin in new[] { "ea165f8d65b6e75b540449e92b4886f43607fa02", "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" })\n        {\n            var previous = Workflow.Replace("actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9", "actions/upload-artifact@" + previousPin, StringComparison.Ordinal);\n            Assert.NotEqual(Workflow, previous);\n            Assert.Throws<InvalidOperationException>(() => WorkflowContractValidator.Validate(previous));\n        }\n    }\n\n', b''), (2467, 2525, b'        BuildAndTest_RejectsPreviousUploadArtifactPins();\n', b''), (6968, 7410, b'        var source = ReadReviewedPreload(auth);\n        ValidateReviewedPreload(source, auth);\n        var currentPin = source.Replace("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02", "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9", StringComparison.Ordinal);\n        Assert.NotEqual(source, currentPin);\n        Assert.Throws<InvalidOperationException>(() => ValidateReviewedPreload(currentPin, auth));\n', b'        ValidateReviewedPreload(ReadReviewedPreload(auth), auth);\n'), (20238, 20354, b'            WorkflowContractValidator.ValidateImagePreloadGroup(steps[7], steps[11], steps[12], historicalFixture);\n', b'            WorkflowContractValidator.ValidateImagePreloadGroup(steps[7], steps[11], steps[12]);\n'), (22234, 22447, b'        var artifactReference = historicalFixture\n            ? "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"\n            : "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9";\n', b''), (22559, 22624, b'            && ((YamlScalarNode)uses).Value == artifactReference\n', b'            && ((YamlScalarNode)uses).Value == "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"\n'), (27708, 27823, b'            ValidateImagePreloadGroup(steps.Children[3], steps.Children[7], steps.Children[8], historicalFixture);\n', b'            ValidateImagePreloadGroup(steps.Children[3], steps.Children[7], steps.Children[8]);\n'), (29530, 29757, b'        RequireScalarValue(evidence, "uses", historicalFixture\n            ? "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"\n            : "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9");\n', b'        RequireScalarValue(evidence, "uses", "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02");\n'), (38627, 38712, b'              uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9\n', b'              uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02\n'), (39881, 39966, b'              uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9\n', b'              uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02\n'), (44589, 44703, b'        RequireScalarValue(evidence, "uses", "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9");\n', b'        RequireScalarValue(evidence, "uses", "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02");\n'), (45501, 45642, b'    internal static void ValidateImagePreloadGroup(YamlNode preloadNode, YamlNode cleanupNode, YamlNode custodyNode, bool historicalFixture)\n', b'    internal static void ValidateImagePreloadGroup(YamlNode preloadNode, YamlNode cleanupNode, YamlNode custodyNode)\n'), (47306, 47532, b'        RequireScalarValue(custody, "uses", historicalFixture\n            ? "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"\n            : "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9");\n', b'        RequireScalarValue(custody, "uses", "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02");\n'))

def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def reconstruct_predecessor(data):
    if (not isinstance(data, bytes) or len(data) != CURRENT_BYTES
            or hashlib.sha256(data).hexdigest() != CURRENT_SHA256 or git_blob(data) != CURRENT_BLOB):
        raise ValueError("Unreviewed current artifact transport source")
    previous = data
    for start, end, current, original in reversed(INVERSE_EDITS):
        if previous[start:end] != current:
            raise ValueError("Current artifact transport inverse differs")
        previous = previous[:start] + original + previous[end:]
    if (len(previous) != PREVIOUS_BYTES or git_blob(previous) != PREVIOUS_BLOB
            or hashlib.sha256(previous).hexdigest() != PREVIOUS_SHA256):
        raise ValueError("Historical artifact transport predecessor differs")
    return previous

def current_workflow_binding(candidate, path, historical, blob, git):
    if path != WORKFLOW:
        return historical
    if historical != PREVIOUS_BLOB:
        raise ValueError("Historical Auth workflow-test binding must remain exact")
    target = candidate / path
    if target.is_symlink() or not stat.S_ISREG(target.stat().st_mode):
        raise ValueError("Current artifact transport source must be a regular file")
    with target.open("rb") as stream:
        data = stream.read(CURRENT_BYTES + 1)
    reconstruct_predecessor(data)
    if (blob(candidate, path) != CURRENT_BLOB
            or git(candidate, "rev-parse", "HEAD:" + path).decode().strip() != CURRENT_BLOB):
        raise ValueError("Current artifact transport working/HEAD identity differs")
    return CURRENT_BLOB
