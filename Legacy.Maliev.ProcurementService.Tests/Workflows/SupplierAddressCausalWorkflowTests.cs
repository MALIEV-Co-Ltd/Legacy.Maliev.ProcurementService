using YamlDotNet.RepresentationModel;

namespace Legacy.Maliev.ProcurementService.Tests.Workflows;

public sealed class SupplierAddressCausalWorkflowTests
{
    private const string Baseline = "95d5b212b64f56ba3dfdfe4abe05b18110fc248d";
    private static string Source => File.ReadAllText(FindWorkflow());

    [Fact]
    public void SupplierAddressCausalRecipe_RequiresSequentialImmutableBaselineAndCandidate()
        => Validate(Source);

    [Fact]
    public void SupplierAddressCausalRecipe_RejectsMutableSkippedOrUnobservedExecution()
    {
        var mutations = new (string Original, string Replacement)[]
        {
            (Baseline, "main"),
            ("timeout-minutes: 30", "timeout-minutes: 0"),
            ("ref: ecb05cbbd68717e415f69df2ac488c1d323b1da3", "ref: main"),
            ("contents: read", "contents: write"),
            ("name: Execute actual baseline33 and observe providers", "name: Execute actual baseline33 and observe providers\n        if: false"),
            ("name: Build candidate before focused execution", "name: Build candidate before focused execution\n        continue-on-error: true"),
            ("python3 -B scripts/observe-supplier-address-providers.py .address-baseline address-causal-results/baseline baseline", "echo baseline"),
            ("python3 -B scripts/observe-supplier-address-providers.py . address-causal-results/candidate candidate", "echo candidate"),
            ("python3 -B scripts/prepare-supplier-address-causal-baseline.py .address-baseline docs/procurement-supplier-address-causal-contract.json --verify-only", "echo identical"),
            ("if: always()", "if: success()"),
            ("path: address-causal-results", "path: runner-results"),
        };
        foreach (var (original, replacement) in mutations)
        {
            Assert.Contains(original, Source, StringComparison.Ordinal);
            Assert.Throws<InvalidOperationException>(() => Validate(Source.Replace(original, replacement, StringComparison.Ordinal)));
        }
    }

    private static void Validate(string source)
    {
        var stream = new YamlStream();
        stream.Load(new StringReader(source));
        var root = (YamlMappingNode)stream.Documents.Single().RootNode;
        var permissions = Map(root, "permissions");
        Require(permissions.Children.Count == 1 && Scalar(permissions, "contents") == "read");
        var jobs = Map(root, "jobs");
        Require(jobs.Children.Count == 1);
        var job = Map(jobs, "address-causal");
        Require(Scalar(job, "runs-on") == "ubuntu-latest" && Scalar(job, "timeout-minutes") == "30");
        var steps = ((YamlSequenceNode)Node(job, "steps")).Children.Cast<YamlMappingNode>().ToArray();
        var names = new[]
        {
            "Check out candidate", "Check out immutable baseline", "Check out accepted Defaults",
            "Check out CompatibilityContracts", "Set up accepted SDK", "Verify causal verifier controls",
            "Bind identical harness and unchanged baseline", "Build baseline before expected assertion failures",
            "Execute actual baseline33 and observe providers", "Require genuine baseline13 assertion failures and20 passes",
            "Build candidate before focused execution", "Execute actual candidate33 and observe providers",
            "Require all candidate33 executions and same harness", "Preserve raw causal and provider evidence",
        };
        Require(steps.Length == names.Length);
        for (var index = 0; index < steps.Length; index++)
        {
            Require(Scalar(steps[index], "name") == names[index]);
            Require(!steps[index].Children.ContainsKey(new YamlScalarNode("continue-on-error")));
            Require(index == 13 || !steps[index].Children.ContainsKey(new YamlScalarNode("if")));
        }
        for (var index = 0; index < 4; index++)
        {
            Require(Scalar(steps[index], "uses") == "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1");
            Require(Scalar(Map(steps[index], "with"), "persist-credentials") == "false");
        }
        Require(Scalar(Map(steps[1], "with"), "ref") == Baseline);
        Require(Scalar(Map(steps[1], "with"), "path") == ".address-baseline");
        Require(Scalar(Map(steps[2], "with"), "ref") == "ecb05cbbd68717e415f69df2ac488c1d323b1da3");
        Require(Scalar(Map(steps[3], "with"), "ref") == "78e48ffc4ee000df0510cba5e7c7a3c4c4d539d7");
        Require(Scalar(steps[4], "uses") == "actions/setup-dotnet@a98b56852c35b8e3190ac28c8c2271da59106c68");
        Require(Scalar(Map(steps[4], "with"), "dotnet-version") == "10.0.x");
        Commands(steps[5], "python3 -B -m unittest discover -s scripts -p test_supplier_address_causal_results.py\n"
            + "python3 -O -B -m unittest discover -s scripts -p test_supplier_address_causal_results.py\n"
            + "python3 -B -m unittest discover -s scripts -p test_supplier_address_provider_observation.py\n"
            + "python3 -O -B -m unittest discover -s scripts -p test_supplier_address_provider_observation.py");
        Commands(steps[6], "python3 -B scripts/prepare-supplier-address-causal-baseline.py .address-baseline docs/procurement-supplier-address-causal-contract.json");
        const string build = "export GITHUB_ACTIONS=false\ndotnet restore Legacy.Maliev.ProcurementService.slnx -p:UseLocalMalievDependencies=true\n"
            + "dotnet build Legacy.Maliev.ProcurementService.slnx --configuration Release --no-restore -warnaserror -p:UseLocalMalievDependencies=true";
        Commands(steps[7], build);
        Require(Scalar(steps[7], "working-directory") == ".address-baseline");
        Commands(steps[10], build);
        foreach (var index in new[] { 7, 10 }) Require(Scalar(steps[index], "timeout-minutes") == "5");
        foreach (var index in new[] { 8, 11 }) Require(Scalar(steps[index], "timeout-minutes") == "6");
        Commands(steps[8], "python3 -B scripts/observe-supplier-address-providers.py .address-baseline address-causal-results/baseline baseline");
        Commands(steps[9], "python3 -B scripts/verify-supplier-address-causal-results.py address-causal-results/baseline docs/procurement-supplier-address-causal-contract.json baseline \"$(cat address-causal-results/baseline/test-exit-code.txt)\"");
        Commands(steps[11], "python3 -B scripts/observe-supplier-address-providers.py . address-causal-results/candidate candidate");
        Commands(steps[12], "python3 -B scripts/verify-supplier-address-causal-results.py address-causal-results/candidate docs/procurement-supplier-address-causal-contract.json candidate \"$(cat address-causal-results/candidate/test-exit-code.txt)\"\n"
            + "python3 -B scripts/prepare-supplier-address-causal-baseline.py .address-baseline docs/procurement-supplier-address-causal-contract.json --verify-only");
        Require(Scalar(steps[13], "if") == "always()");
        Require(Scalar(steps[13], "uses") == "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02");
        Require(Scalar(Map(steps[13], "with"), "path") == "address-causal-results");
    }

    private static void Commands(YamlMappingNode node, string expected)
        => Require(Scalar(node, "run").Replace("\r\n", "\n", StringComparison.Ordinal).Trim() == expected);

    private static void Require(bool value)
    {
        if (!value) throw new InvalidOperationException("Supplier address causal recipe differs from reviewed execution contract.");
    }

    private static YamlNode Node(YamlMappingNode node, string key)
        => node.Children.TryGetValue(new YamlScalarNode(key), out var value) ? value
            : throw new InvalidOperationException($"Missing causal workflow key: {key}.");

    private static YamlMappingNode Map(YamlMappingNode node, string key) => (YamlMappingNode)Node(node, key);
    private static string Scalar(YamlMappingNode node, string key) => ((YamlScalarNode)Node(node, key)).Value ?? string.Empty;

    private static string FindWorkflow()
    {
        for (DirectoryInfo? directory = new DirectoryInfo(AppContext.BaseDirectory); directory is not null; directory = directory.Parent)
        {
            var path = Path.Combine(directory.FullName, ".github", "workflows", "procurement-supplier-address-causal-validation.yml");
            if (File.Exists(path)) return path;
        }
        throw new FileNotFoundException("Supplier address causal workflow was not found.");
    }
}
