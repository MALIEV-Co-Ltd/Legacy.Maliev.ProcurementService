using System.Text.RegularExpressions;
using System.Text.Json;

using YamlDotNet.Core;
using YamlDotNet.RepresentationModel;

namespace Legacy.Maliev.ProcurementService.Tests.Workflows;

public sealed class WorkflowContractTests
{
    private const string ReviewedProducerVersion = "b27fbef06a3aa58c1f4fc0e75d7c70b32be76266";
    private const string HistoricalProcurementVersion = "c40fd246c17b738879c9345c6bcca44d96faf025";
    private const string PreviousProcurementVersion = "99049bab2c100ffdf6606bf11a2f50980c0cf3cf";
    private const string ReviewedDiagnosticProducerVersion = "7dc13204317176a3f8a970443af99c563ca14b37";
    private const string RetainedOwnerCorrelationVersion = "4a117fb68cebffc9e0acae9000750e8e45ec62cc";
    private static readonly string Workflow = File.ReadAllText(FindRepositoryFile(".github", "workflows", "_build-and-test.yml"));
    private static readonly string ApiProject = File.ReadAllText(
        FindRepositoryFile("Legacy.Maliev.ProcurementService.Api", "Legacy.Maliev.ProcurementService.Api.csproj"));
    private static readonly string DataProject = File.ReadAllText(
        FindRepositoryFile("Legacy.Maliev.ProcurementService.Data", "Legacy.Maliev.ProcurementService.Data.csproj"));

    [Fact]
    public void BuildAndTest_SatisfiesStructuralContract()
    {
        WorkflowContractValidator.Validate(Workflow);
        foreach (var (original, replacement) in new[]
        {
            ("--no-restore -warnaserror", "--no-restore"),
            ("FullyQualifiedName~ProcurementDurableDiagnosticPolicyTests", "FullyQualifiedName~OtherTests"),
            ("FullyQualifiedName~ProcurementDurableCreateTests|FullyQualifiedName~ProcurementDurableChildCreateTests", "FullyQualifiedName~ProcurementDurableCreateTests"),
            ("name: Require diagnostic focused source enrollment", "name: Omitted diagnostic source enrollment"),
            ("name: Require every diagnostic focused execution\n        timeout-minutes: 1\n        if: always()", "name: Require every diagnostic focused execution\n        timeout-minutes: 1\n        if: success()"),
            ("path: durable-focused-results", "path: runner-results"),
            ("name: Execute durable focused regressions\n        timeout-minutes: 5", "name: Execute durable focused regressions\n        timeout-minutes: 5\n        continue-on-error: true"),
            ("-p:UseLocalMalievDependencies=true", "-p:UseLocalMalievDependencies=false"),
            ("export GITHUB_ACTIONS=false", "export GITHUB_ACTIONS=true"),
            ("      MALIEV_FINITE_OWNER_SOURCE_HEAD: ${{ github.event.pull_request.head.sha || github.sha }}\n", ""),
            ("      MALIEV_FINITE_OWNER_SOURCE_HEAD: ${{ github.event.pull_request.head.sha || github.sha }}", "      MALIEV_FINITE_OWNER_SOURCE_HEAD: ${{ github.sha }}"),
            ("      MALIEV_FINITE_OWNER_DISCOVERY: 'qualified-full-only'\n", ""),
            ("      MALIEV_FINITE_OWNER_DISCOVERY: 'qualified-full-only'", "      MALIEV_FINITE_OWNER_DISCOVERY: 'reviewed-source-only'"),
            ("          fetch-depth: 0\n", ""),
            ("          fetch-depth: 0", "          fetch-depth: 2"),
            ("          fetch-depth: 0", "          fetch-depth: 3"),
            ("      MALIEV_FINITE_OWNER_DISCOVERY: 'qualified-full-only'", "      MALIEV_FINITE_OWNER_DISCOVERY: 'qualified-full-only'\n      UNREVIEWED_OWNER_OPTION: true"),
            ("          fetch-depth: 0", "          fetch-depth: 0\n          unreviewed-input: true"),
            ("python3 -B scripts/verify-procurement-fixture-containment.py --source-admission", "echo source-admission-omitted"),
            ("python3 -B scripts/verify-procurement-fixture-containment.py --source-admission", "python3 -B scripts/verify-procurement-fixture-containment.py --provisional-discovery"),
            ("python3 -B scripts/verify-procurement-fixture-containment.py --source-admission\n          dotnet restore Legacy.Maliev.ProcurementService.slnx -p:UseLocalMalievDependencies=true", "dotnet restore Legacy.Maliev.ProcurementService.slnx -p:UseLocalMalievDependencies=true\n          python3 -B scripts/verify-procurement-fixture-containment.py --source-admission"),
            ("name: Set up SDK for mandatory focused workflow checks", "name: Omitted mandatory SDK"),
            ("name: Build before mandatory focused workflow checks", "name: Execute mandatory focused workflow checks"),
            ("name: Execute mandatory focused workflow checks", "name: Execute mandatory focused workflow checks\n        if: false"),
            ("FullyQualifiedName~ActualAuthProgramJoin|FullyQualifiedName~ReviewedImagePreload", "FullyQualifiedName~ReviewedImagePreload"),
            ("path: focused-workflow-results", "path: runner-results"),
            ("name: Require every focused workflow execution\n        if: always()", "name: Require every focused workflow execution\n        if: success()"),
            ("name: Preserve focused workflow evidence\n        if: always()", "name: Preserve focused workflow evidence\n        if: success()"),
            ("name: Build before mandatory focused workflow checks", "name: Build before mandatory focused workflow checks\n        continue-on-error: true"),
        })
            AssertMutationRejected(original, replacement);
    }

    [Fact]
    public void ContainmentSourceCheckout_RequiresFullHistoryAndSanitizedCredentials()
    {
        var workflow = File.ReadAllText(FindRepositoryFile(".github", "workflows", "procurement-fixture-containment.yml"))
            .Replace("\r\n", "\n", StringComparison.Ordinal);
        WorkflowContractValidator.ValidateContainmentSourceCheckout(workflow);
        foreach (var (original, replacement) in new[]
        {
            ("          fetch-depth: 0\n", ""),
            ("          fetch-depth: 0", "          fetch-depth: 3"),
            ("          fetch-depth: 0", "          fetch-depth: 2"),
            ("          fetch-depth: 0", "          fetch-depth: 0\n          unreviewed-input: true"),
            ("          persist-credentials: false", "          persist-credentials: true"),
        })
        {
            Assert.Contains(original, workflow, StringComparison.Ordinal);
            Assert.Throws<InvalidOperationException>(() => WorkflowContractValidator.ValidateContainmentSourceCheckout(
                workflow.Replace(original, replacement, StringComparison.Ordinal)));
        }
    }

    [Fact]
    public void StartupJournalWorkflow_RejectsOmissionOrderingAndValidationDrift()
    {
        foreach (var (original, replacement) in new[]
        {
            ("FullyQualifiedName~ProcurementFixtureOwnerCorrelationTests", "FullyQualifiedName~OtherTests"),
            ("name: Execute owner correlation regressions\n        timeout-minutes: 2", "name: Execute owner correlation regressions\n        timeout-minutes: 3"),
            ("name: Execute owner correlation regressions\n        timeout-minutes: 2", "name: Execute owner correlation regressions\n        timeout-minutes: 2\n        if: false"),
            ("name: Execute owner correlation regressions\n        timeout-minutes: 2", "name: Execute owner correlation regressions\n        timeout-minutes: 2\n        continue-on-error: true"),
            ("name: Require every owner correlation execution\n        timeout-minutes: 1", "name: Require every owner correlation execution\n        timeout-minutes: 0"),
            ("python3 -B scripts/verify-owner-correlation-results.py owner-correlation-results", "echo owner-gate-skipped"),
            ("python3 -B -O -m unittest discover -s scripts -p test_owner_correlation_results.py", "echo owner-controls-skipped"),
            ("name: Preserve owner correlation evidence\n        timeout-minutes: 1", "name: Preserve owner correlation evidence\n        timeout-minutes: 0"),
            ("path: owner-correlation-results", "path: foreign-results"),
            ("FullyQualifiedName~ProcurementFixtureStartupJournalTests", "FullyQualifiedName~OtherTests"),
            ("name: Execute startup journal regressions\n        timeout-minutes: 2", "name: Execute startup journal regressions\n        timeout-minutes: 3"),
            ("name: Execute startup journal regressions\n        timeout-minutes: 2", "name: Execute startup journal regressions\n        timeout-minutes: 2\n        if: false"),
            ("name: Execute startup journal regressions\n        timeout-minutes: 2", "name: Execute startup journal regressions\n        timeout-minutes: 2\n        continue-on-error: true"),
            ("python3 -B scripts/verify-startup-journal-results.py startup-journal-results", "python3 -B scripts/verify-startup-journal-results.py foreign-results"),
            ("python3 -B -O -m unittest discover -s scripts -p test_startup_journal_results.py", "echo skipped"),
            ("name: Require every startup journal execution\n        if: always()", "name: Require every startup journal execution\n        if: failure()"),
            ("name: Preserve startup journal evidence\n        if: always()", "name: Preserve startup journal evidence\n        if: success()"),
            ("name: procurement-startup-journal-${{ github.sha }}", "name: foreign-${{ github.sha }}"),
            ("path: startup-journal-results", "path: foreign-results"),
        })
        {
            var source = Workflow.Replace("\r\n", "\n", StringComparison.Ordinal);
            Assert.Contains(original, source, StringComparison.Ordinal);
            Assert.Throws<InvalidOperationException>(() => WorkflowContractValidator.Validate(source.Replace(original, replacement, StringComparison.Ordinal)));
        }
        foreach (var mutation in new[] { "omit-test", "omit-gate", "omit-upload", "reorder", "extra", "omit-owner-test", "omit-owner-gate", "omit-owner-upload", "reorder-owner" })
        {
            var yaml = new YamlStream();
            yaml.Load(new StringReader(Workflow));
            var root = (YamlMappingNode)yaml.Documents[0].RootNode;
            var jobs = (YamlMappingNode)root.Children[new YamlScalarNode("jobs")];
            var job = (YamlMappingNode)jobs.Children[new YamlScalarNode("validate")];
            var steps = (YamlSequenceNode)job.Children[new YamlScalarNode("steps")];
            if (mutation == "reorder") (steps.Children[8], steps.Children[9]) = (steps.Children[9], steps.Children[8]);
            else if (mutation == "reorder-owner") (steps.Children[11], steps.Children[12]) = (steps.Children[12], steps.Children[11]);
            else if (mutation.StartsWith("omit-owner-", StringComparison.Ordinal)) steps.Children.RemoveAt(mutation == "omit-owner-test" ? 11 : mutation == "omit-owner-gate" ? 12 : 13);
            else if (mutation == "extra") steps.Children.Add(new YamlMappingNode(new YamlScalarNode("run"), new YamlScalarNode("echo extra")));
            else steps.Children.RemoveAt(mutation == "omit-test" ? 8 : mutation == "omit-gate" ? 9 : 10);
            using var writer = new StringWriter();
            yaml.Save(writer, assignAnchors: false);
            Assert.Throws<InvalidOperationException>(() => WorkflowContractValidator.Validate(writer.ToString()));
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void ReviewedImagePreload_PreservesValidationAndSeparateEvidence(bool auth)
    {
        ValidateReviewedPreload(ReadReviewedPreload(auth), auth);
    }

    [Theory]
    [InlineData(false, "timeout-minutes: 5", "timeout-minutes: 6")]
    [InlineData(true, "timeout-minutes: 5", "timeout-minutes: 6")]
    [InlineData(false, "timeout-minutes: 2", "timeout-minutes: 3")]
    [InlineData(true, "timeout-minutes: 2", "timeout-minutes: 3")]
    [InlineData(false, "python3 -B -O scripts/ci-postgres-preload/test_preload_official_postgres.py", "python3 -B scripts/ci-postgres-preload/test_preload_official_postgres.py")]
    [InlineData(true, "python3 -B -O scripts/ci-postgres-preload/test_preload_official_postgres.py", "python3 -B scripts/ci-postgres-preload/test_preload_official_postgres.py")]
    [InlineData(false, "preload_official_postgres.py cleanup", "preload_official_postgres.py cleanup --all")]
    [InlineData(true, "preload_official_postgres.py cleanup", "preload_official_postgres.py cleanup --all")]
    [InlineData(false, "name: Release owned image preload tags\n        if: always()", "name: Release owned image preload tags\n        if: success()")]
    [InlineData(true, "name: Release owned image preload tags\n        if: always()", "name: Release owned image preload tags\n        if: success()")]
    [InlineData(false, "name: Preserve image custody evidence\n        if: always()", "name: Preserve image custody evidence\n        if: success()")]
    [InlineData(true, "name: Preserve image custody evidence\n        if: always()", "name: Preserve image custody evidence\n        if: success()")]
    [InlineData(false, "${{ runner.temp }}/procurement-postgres-preload.json", "${{ runner.temp }}/foreign.json")]
    [InlineData(true, "${{ runner.temp }}/procurement-postgres-preload.json", "${{ runner.temp }}/foreign.json")]
    [InlineData(false, "retention-days: 7", "retention-days: 30")]
    [InlineData(true, "retention-days: 7", "retention-days: 30")]
    [InlineData(false, "timeout-minutes: 5\n        run:", "timeout-minutes: 5\n        env:\n          GITHUB_ACTIONS: 'false'\n        run:")]
    [InlineData(true, "timeout-minutes: 5\n        run:", "timeout-minutes: 5\n        env:\n          GITHUB_ACTIONS: 'false'\n        run:")]
    public void ReviewedImagePreload_RejectsControlCleanupAndCustodyDrift(bool auth, string original, string replacement)
    {
        var source = ReadReviewedPreload(auth);
        Assert.Contains(original, source, StringComparison.Ordinal);
        Assert.Throws<InvalidOperationException>(() => ValidateReviewedPreload(source.Replace(original, replacement, StringComparison.Ordinal), auth));
    }

    private static string ReadReviewedPreload(bool auth) => File.ReadAllText(FindRepositoryFile(
        "Legacy.Maliev.ProcurementService.Tests", "Workflows", "Fixtures", auth ? "reviewed-preload-auth.yml" : "reviewed-preload-build.yml"));

    private static void ValidateReviewedPreload(string source, bool auth)
    {
        if (auth) ValidateAuthProgramJoin(source, historicalFixture: true);
        else WorkflowContractValidator.Validate(source, historicalFixture: true);
    }

    [Fact]
    public void DependabotConfiguration_ScansOnlyIndependentlyResolvableProjectDirectories()
    {
        var source = File.ReadAllText(FindRepositoryFile(".github", "dependabot.yml"));
        var yaml = new YamlStream();
        yaml.Load(new StringReader(source));

        var root = Assert.IsType<YamlMappingNode>(Assert.Single(yaml.Documents).RootNode);
        var updates = Assert.IsType<YamlSequenceNode>(ReadNode(root, "updates"));
        var nuget = updates.Children
            .Select(Assert.IsType<YamlMappingNode>)
            .Single(update => ReadScalar(update, "package-ecosystem") == "nuget");
        var directories = Assert.IsType<YamlSequenceNode>(ReadNode(nuget, "directories"));

        Assert.Equal(
            [
                "/Legacy.Maliev.ProcurementService.Application",
                "/Legacy.Maliev.ProcurementService.Data",
                "/Legacy.Maliev.ProcurementService.Domain",
            ],
            directories.Children.Select(Assert.IsType<YamlScalarNode>).Select(node => node.Value));
        Assert.False(nuget.Children.ContainsKey(new YamlScalarNode("directory")));
        Assert.False(nuget.Children.ContainsKey(new YamlScalarNode("exclude-paths")));
    }

    [Fact]
    public void DependabotConfiguration_AllowsCoordinatedEfUpdatesAndDefersSharedRuntimePackages()
    {
        var source = File.ReadAllText(FindRepositoryFile(".github", "dependabot.yml"));
        var yaml = new YamlStream();
        yaml.Load(new StringReader(source));

        var root = Assert.IsType<YamlMappingNode>(Assert.Single(yaml.Documents).RootNode);
        var updates = Assert.IsType<YamlSequenceNode>(ReadNode(root, "updates"));
        var nuget = updates.Children
            .Select(Assert.IsType<YamlMappingNode>)
            .Single(update => ReadScalar(update, "package-ecosystem") == "nuget");
        var ignored = Assert.IsType<YamlSequenceNode>(ReadNode(nuget, "ignore"));
        var rules = ignored.Children.Select(Assert.IsType<YamlMappingNode>).ToArray();

        Assert.Equal(
            [
                "Legacy.Maliev.ServiceDefaults",
                "Legacy.Maliev.CompatibilityContracts",
            ],
            rules.Select(rule => ReadScalar(rule, "dependency-name")));
    }

    [Fact]
    public void BuildAndTest_RejectsSharedActionMainWithPinnedShaComment()
    {
        AssertMutationRejected(
            "MALIEV-Co-Ltd/Legacy.Maliev.Workflows/actions/dotnet-validate@e3a6093324a24968876782153286f52db8b29fd8",
            "MALIEV-Co-Ltd/Legacy.Maliev.Workflows/actions/dotnet-validate@main # e3a6093324a24968876782153286f52db8b29fd8");
    }

    [Fact]
    public void BuildAndTest_RejectsCommentedDependencySha()
    {
        AssertMutationRejected(
            "ref: ecb05cbbd68717e415f69df2ac488c1d323b1da3",
            "ref: main # ecb05cbbd68717e415f69df2ac488c1d323b1da3");
    }

    [Fact]
    public void BuildAndTest_RejectsMissingOwnedCoverageGate()
    {
        AssertMutationRejected(
            "      - name: Gate owned production coverage\n        run: python3 scripts/verify-runner-coverage.py runner-results\n",
            string.Empty);
    }

    [Fact]
    public void BuildAndTest_RejectsEvidenceThatDoesNotSurviveFailure()
    {
        AssertMutationRejected("        if: always()", "        if: success()");
    }

    [Fact]
    public void ApiProject_UsesOnlyLegacyServiceDefaults()
    {
        Assert.Contains("Legacy.Maliev.ServiceDefaults", ApiProject, StringComparison.Ordinal);
        Assert.DoesNotContain("Maliev.Aspire\\Maliev.Aspire.ServiceDefaults", ApiProject, StringComparison.Ordinal);
        Assert.DoesNotContain("Include=\"Maliev.Aspire.ServiceDefaults\"", ApiProject, StringComparison.Ordinal);
    }

    [Fact]
    public void EfDesignDependency_IsOwnedByDataProjectOnly()
    {
        Assert.DoesNotContain("Microsoft.EntityFrameworkCore.Design", ApiProject, StringComparison.Ordinal);
        Assert.Contains("Microsoft.EntityFrameworkCore.Design", DataProject, StringComparison.Ordinal);
    }

    [Fact]
    public void BuildAndTest_RejectsJobPermissionEscalation()
    {
        AssertMutationRejected(
            "  validate:\n    name: validate",
            "  validate:\n    permissions:\n      contents: write\n    name: validate");
    }

    [Fact]
    public void BuildAndTest_RejectsSecretReferenceAnywhere()
    {
        var mutated = $"{Workflow}\n# ${{{{ secrets.X }}}}\n";

        Assert.Throws<InvalidOperationException>(() => WorkflowContractValidator.Validate(mutated));
    }

    [Theory]
    [InlineData("${{secrets.X}}")]
    [InlineData("${{ secrets['X'] }}")]
    public void BuildAndTest_RejectsSecretExpressionInJobEnvironment(string expression)
    {
        AssertMutationRejected(
            "      MalievWorkspaceRoot: ${{ github.workspace }}/.dependencies",
            $"      MalievWorkspaceRoot: ${{{{ github.workspace }}}}/.dependencies\n      REVIEW_TOKEN: {expression}");
    }

    [Fact]
    public void BuildAndTest_RejectsWhitespaceObfuscatedRestoreCommand()
    {
        AssertMutationRejected(
            "          solution: Legacy.Maliev.ProcurementService.slnx",
            "          solution: Legacy.Maliev.ProcurementService.slnx\n      - run: dotnet  restore Legacy.Maliev.ProcurementService.slnx");
    }

    [Fact]
    public void BuildAndTest_RejectsMissingLocalDependencyOptIn()
    {
        AssertMutationRejected(
            "          use-local-maliev-dependencies: 'true'\n",
            string.Empty);
    }

    [Fact]
    public void BuildAndTest_RejectsReservedGitHubActionsOverride()
    {
        AssertMutationRejected(
            "          use-local-maliev-dependencies: 'true'\n",
            "          use-local-maliev-dependencies: 'true'\n        env:\n          GITHUB_ACTIONS: 'false'\n");
    }

    [Fact]
    public void ActualAuthProgramJoin_RequiresImmutableProducersAndAlwaysRetainedEvidence()
    {
        var source = File.ReadAllText(FindRepositoryFile(".github", "workflows", "procurement-auth-program-validation.yml"));
        ValidateAuthProgramJoin(source);
        foreach (var (original, replacement) in new[]
        {
            ("          fetch-depth: 0", "          fetch-depth: 1"),
            (" --joined-root .joined-public", " --joined-root foreign"),
            (" --source-head", " --historical-downgrade"),
            ("python3 -B -O -m unittest", "echo skipped"),
            ("inputs .joined-public", "inputs foreign"),
        })
        {
            Assert.Contains(original, source, StringComparison.Ordinal);
            Assert.Throws<InvalidOperationException>(() => ValidateAuthProgramJoin(source.Replace(original, replacement, StringComparison.Ordinal)));
        }
    }

    [Theory]
    [InlineData("b27fbef06a3aa58c1f4fc0e75d7c70b32be76266", "main")]
    [InlineData("ecb05cbbd68717e415f69df2ac488c1d323b1da3", "7edcd961024868513fd5f373cab3dcb261197f77")]
    [InlineData("c40fd246c17b738879c9345c6bcca44d96faf025", "main")]
    [InlineData("99049bab2c100ffdf6606bf11a2f50980c0cf3cf", "main")]
    [InlineData("if: always()", "if: failure()")]
    [InlineData("python3 -B scripts/verify-procurement-auth-program.py results auth-program-results", "python3 -c 'print(0)'")]
    public void ActualAuthProgramJoin_RejectsMutableProducerOrMissingAcceptanceGate(string original, string replacement)
    {
        var historical = original == HistoricalProcurementVersion;
        var source = historical ? ReadReviewedPreload(auth: true)
            : File.ReadAllText(FindRepositoryFile(".github", "workflows", "procurement-auth-program-validation.yml"));
        var activePin = original == PreviousProcurementVersion ? ReviewedDiagnosticProducerVersion : original;
        Assert.Contains(activePin, source, StringComparison.Ordinal);
        Assert.Throws<InvalidOperationException>(() => ValidateAuthProgramJoin(source.Replace(activePin, replacement, StringComparison.Ordinal), historicalFixture: historical));
    }

    private static void ValidateAuthProgramJoin(string source, bool historicalFixture = false)
    {
        string? diagnosticProducer = null;
        if (!historicalFixture)
        {
            using var manifest = JsonDocument.Parse(File.ReadAllText(FindRepositoryFile("tools", "ProcurementAuthProgram.Tests", "public-graph-fixture-owner-correlation.json")));
            var graph = manifest.RootElement;
            if (graph.GetProperty("schemaVersion").GetRawText() != "2"
                || graph.GetProperty("graphId").GetString() != "procurement-auth-diagnostic-dependencies-v2")
                throw new InvalidOperationException("Require exact diagnostic-v2 graph.");
            var binding = graph.GetProperty("diagnosticDependencySourceBinding");
            diagnosticProducer = binding.GetProperty("reviewedProducer").GetString();
            if (diagnosticProducer != ReviewedDiagnosticProducerVersion
                || binding.GetProperty("fixtureInputCount").GetRawText() != "16"
                || binding.GetProperty("inputCount").GetRawText() != "82"
                || binding.GetProperty("productionBuildInputCount").GetRawText() != "66"
                || (diagnosticProducer is null && binding.GetProperty("releaseAllowed").GetRawText() != "false")
                || (diagnosticProducer is not null && (!Regex.IsMatch(diagnosticProducer, "^[0-9a-f]{40}$")
                    || binding.GetProperty("releaseAllowed").GetRawText() != "true")))
                throw new InvalidOperationException("Diagnostic producer admission must remain exact and inactive until bound.");
        }
        var yaml = new YamlStream();
        yaml.Load(new StringReader(source));
        var root = (YamlMappingNode)yaml.Documents.Single().RootNode;
        var job = (YamlMappingNode)ReadNode((YamlMappingNode)ReadNode(root, "jobs"), "auth-program");
        var steps = ((YamlSequenceNode)ReadNode(job, "steps")).Children.Cast<YamlMappingNode>().ToArray();
        if (steps.Length == 13)
        {
            if (ReadScalar(job, "timeout-minutes") != "30")
                throw new InvalidOperationException("Image preload must retain the bounded job deadline.");
            WorkflowContractValidator.ValidateImagePreloadGroup(steps[7], steps[11], steps[12]);
        }
        else if (steps.Length != 10)
        {
            throw new InvalidOperationException("Auth join must contain only its original steps or the reviewed image preload group.");
        }
        var expected = new (string Repository, string Commit)[]
        {
            ("MALIEV-Co-Ltd/Legacy.Maliev.AuthService", ReviewedProducerVersion),
            ("MALIEV-Co-Ltd/Legacy.Maliev.ServiceDefaults", "ecb05cbbd68717e415f69df2ac488c1d323b1da3"),
            ("MALIEV-Co-Ltd/Legacy.Maliev.CompatibilityContracts", "78e48ffc4ee000df0510cba5e7c7a3c4c4d539d7"),
            ("MALIEV-Co-Ltd/Legacy.Maliev.ProcurementService", historicalFixture ? HistoricalProcurementVersion : diagnosticProducer ?? RetainedOwnerCorrelationVersion),
        }.ToDictionary(entry => entry.Repository, entry => entry.Commit);
        var checkouts = steps.Where(step => step.Children.TryGetValue(new YamlScalarNode("with"), out var node)
            && node is YamlMappingNode settings && settings.Children.ContainsKey(new YamlScalarNode("repository"))).ToArray();
        if (checkouts.Length != expected.Count) throw new InvalidOperationException("Require exactly the four reviewed producer checkouts.");
        foreach (var checkout in checkouts)
        {
            var settings = (YamlMappingNode)ReadNode(checkout, "with");
            if (!expected.TryGetValue(ReadScalar(settings, "repository"), out var pin) || ReadScalar(settings, "ref") != pin
                || ReadScalar(settings, "persist-credentials") != "false")
                throw new InvalidOperationException("Producer checkout must retain its reviewed hard pin without credentials.");
        }
        var evidence = " --owned-head \"${{ github.sha }}\" --source-head \"${{ github.event.pull_request.head.sha || github.sha }}\"";
        var resultsCommand = "python3 -B scripts/verify-procurement-auth-program.py results auth-program-results"
            + (historicalFixture ? "" : " --joined-root .joined-public" + evidence);
        if (!historicalFixture)
        {
            var owned = (YamlMappingNode)ReadNode(steps[0], "with");
            var witness = (YamlMappingNode)ReadNode(checkouts.Single(step => ReadScalar((YamlMappingNode)ReadNode(step, "with"), "repository") == "MALIEV-Co-Ltd/Legacy.Maliev.ProcurementService"), "with");
            if (ReadScalar(owned, "persist-credentials") != "false" || ReadScalar(owned, "fetch-depth") != "0"
                || ReadScalar(witness, "fetch-depth") != "0")
                throw new InvalidOperationException("Both owned and witness checkouts require complete sanitized history.");
            var input = steps.Single(step => step.Children.TryGetValue(new YamlScalarNode("run"), out var command)
                && ((YamlScalarNode)command).Value == "python3 -B scripts/verify-procurement-auth-program.py inputs .joined-public" + evidence);
            if (!ReferenceEquals(input, steps[5]))
                throw new InvalidOperationException("Source admission must precede controls and native join.");
            if (input.Children.ContainsKey(new YamlScalarNode("if")) || input.Children.ContainsKey(new YamlScalarNode("continue-on-error")))
                throw new InvalidOperationException("Input admission cannot be bypassed.");
            var controls = steps.Single(step => ReadScalar(step, "name") == "Require runtime input guard mutation controls");
            if (!ReferenceEquals(controls, steps[6]))
                throw new InvalidOperationException("Controls must precede native join.");
            if (ReadScalar(controls, "run").Trim() != "python3 -B -m unittest discover -s scripts -p test_procurement_auth_program_inputs.py\npython3 -B -O -m unittest discover -s scripts -p test_procurement_auth_program_inputs.py")
                throw new InvalidOperationException("Normal and optimized mutation controls are required.");
        }
        var results = steps.Single(step => step.Children.TryGetValue(new YamlScalarNode("run"), out var run)
            && ((YamlScalarNode)run).Value == resultsCommand);
        var artifact = steps.Single(step => step.Children.TryGetValue(new YamlScalarNode("uses"), out var uses)
            && ((YamlScalarNode)uses).Value == "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
            && step.Children.TryGetValue(new YamlScalarNode("with"), out var settings)
            && settings is YamlMappingNode inputs
            && inputs.Children.TryGetValue(new YamlScalarNode("path"), out var path)
            && path is YamlScalarNode { Value: "auth-program-results" });
        if (ReadScalar(results, "if") != "always()" || ReadScalar(artifact, "if") != "always()"
            || ReadScalar((YamlMappingNode)ReadNode(artifact, "with"), "path") != "auth-program-results")
            throw new InvalidOperationException("Joined executions and failure evidence must always be checked/retained.");
    }

    private static void AssertMutationRejected(string original, string replacement)
    {
        Assert.Contains(original, Workflow, StringComparison.Ordinal);
        var mutated = Workflow.Replace(original, replacement, StringComparison.Ordinal);

        Assert.Throws<InvalidOperationException>(() => WorkflowContractValidator.Validate(mutated));
    }

    private static YamlNode ReadNode(YamlMappingNode mapping, string key)
    {
        return mapping.Children[new YamlScalarNode(key)];
    }

    private static string ReadScalar(YamlMappingNode mapping, string key)
    {
        return Assert.IsType<YamlScalarNode>(ReadNode(mapping, key)).Value
            ?? throw new InvalidOperationException($"Expected '{key}' to have a scalar value.");
    }

    private static string FindRepositoryFile(params string[] segments)
    {
        DirectoryInfo? directory = new(AppContext.BaseDirectory);

        while (directory is not null)
        {
            var candidate = Path.Combine([directory.FullName, .. segments]);
            if (File.Exists(candidate))
            {
                return candidate;
            }

            directory = directory.Parent;
        }

        throw new FileNotFoundException($"Could not find repository file '{Path.Combine(segments)}'.");
    }
}

internal static partial class WorkflowContractValidator
{
    private const string CheckoutAction = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1";
    private const string SharedValidationAction = "MALIEV-Co-Ltd/Legacy.Maliev.Workflows/actions/dotnet-validate@e3a6093324a24968876782153286f52db8b29fd8";

    internal static void ValidateContainmentSourceCheckout(string workflow)
    {
        var yaml = new YamlStream();
        yaml.Load(new StringReader(workflow));
        var root = RequireMapping(yaml.Documents.Single().RootNode, "containment workflow");
        var jobs = RequireMapping(root, "jobs");
        var job = RequireMapping(jobs, "containment");
        var steps = RequireSequence(job, "steps");
        RequireScalarValue(RequireMapping(steps.Children[0], "owned source checkout"), "name", "Check out owned source");
        ValidateStep(steps.Children[0], CheckoutAction, new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["persist-credentials"] = "false",
            ["fetch-depth"] = "0",
        });
    }

    public static void Validate(string workflow, bool historicalFixture = false)
    {
        if (SecretExpression().IsMatch(workflow))
        {
            throw new InvalidOperationException("Workflow must not reference secrets.");
        }

        var yaml = new YamlStream();
        try
        {
            yaml.Load(new StringReader(workflow));
        }
        catch (Exception exception)
        {
            throw new InvalidOperationException("Workflow must be valid YAML.", exception);
        }

        if (yaml.Documents.Count != 1 || yaml.Documents[0].RootNode is not YamlMappingNode root)
        {
            throw new InvalidOperationException("Workflow must contain exactly one mapping document.");
        }

        var workflowPermissions = RequireExactReadOnlyPermissions(RequireMapping(root, "permissions"), "workflow");
        var jobs = RequireMapping(root, "jobs");
        if (jobs.Children.Count != 1)
        {
            throw new InvalidOperationException("Workflow must define only the validate job.");
        }

        var validateJob = RequireMapping(jobs, "validate");
        var jobPermissionsNode = GetOptional(validateJob, "permissions");
        var effectiveJobPermissions = jobPermissionsNode is null
            ? workflowPermissions
            : RequireExactReadOnlyPermissions(RequireMapping(jobPermissionsNode, "jobs.validate.permissions"), "validate job");
        if (!effectiveJobPermissions.SequenceEqual(workflowPermissions, StringComparer.Ordinal))
        {
            throw new InvalidOperationException("Validate job permissions must not differ from workflow permissions.");
        }

        RequireScalarValue(validateJob, "name", "validate");

        var steps = RequireSequence(validateJob, "steps");
        if (!historicalFixture)
        {
            ValidateFocusedWorkflowGroup(steps);
            steps = new YamlSequenceNode(steps.Children.Where((_, index) => index is < 3 or > 20));
        }
        RejectDuplicatedValidationActionsAndCommands(steps);
        if (steps.Children.Count == 9)
        {
            RequireScalarValue(validateJob, "timeout-minutes", "30");
            ValidateImagePreloadGroup(steps.Children[3], steps.Children[7], steps.Children[8]);
            steps = new YamlSequenceNode(steps.Children.Where((_, index) => index is not (3 or 7 or 8)));
        }
        if (steps.Children.Count != 6)
        {
            throw new InvalidOperationException("Validate job must contain four validation and two evidence steps.");
        }

        var environment = RequireMapping(validateJob, "env");
        if (environment.Children.Count != (historicalFixture ? 4 : 6))
        {
            throw new InvalidOperationException("Validate environment must contain exactly the approved source admission, dependency root and evidence properties.");
        }

        if (!historicalFixture)
        {
            RequireScalarValue(environment, "MALIEV_FINITE_OWNER_SOURCE_HEAD", "${{ github.event.pull_request.head.sha || github.sha }}");
            RequireScalarValue(environment, "MALIEV_FINITE_OWNER_DISCOVERY", "qualified-full-only");
        }

        RequireScalarValue(environment, "MalievWorkspaceRoot", "${{ github.workspace }}/.dependencies");
        RequireScalarValue(environment, "VSTestCollect", "XPlat Code Coverage");
        RequireScalarValue(environment, "VSTestLogger", "trx");
        RequireScalarValue(environment, "VSTestResultsDirectory", "${{ github.workspace }}/runner-results");

        var gate = RequireMapping(steps.Children[4], "coverage gate");
        if (gate.Children.Count != 2)
        {
            throw new InvalidOperationException("Coverage gate must contain only name and run.");
        }

        RequireScalarValue(gate, "name", "Gate owned production coverage");
        RequireScalarValue(gate, "run", "python3 scripts/verify-runner-coverage.py runner-results");
        var evidence = RequireMapping(steps.Children[5], "evidence upload");
        if (evidence.Children.Count != 4)
        {
            throw new InvalidOperationException("Evidence upload must contain exactly name, if, uses and with.");
        }

        RequireScalarValue(evidence, "name", "Preserve validation evidence");
        RequireScalarValue(evidence, "if", "always()");
        RequireScalarValue(evidence, "uses", "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02");
        var evidenceInputs = RequireMapping(evidence, "with");
        if (evidenceInputs.Children.Count != 4)
        {
            throw new InvalidOperationException("Evidence upload must have exactly four bounded inputs.");
        }

        RequireScalarValue(evidenceInputs, "name", "procurement-validation-${{ github.sha }}");
        RequireScalarValue(evidenceInputs, "path", "runner-results");
        RequireScalarValue(evidenceInputs, "if-no-files-found", "warn");
        RequireScalarValue(evidenceInputs, "retention-days", "7");

        var sourceCheckoutInputs = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["persist-credentials"] = "false",
        };
        if (!historicalFixture) sourceCheckoutInputs.Add("fetch-depth", "0");
        ValidateStep(steps.Children[0], CheckoutAction, sourceCheckoutInputs);
        ValidateStep(
            steps.Children[1],
            CheckoutAction,
            new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["repository"] = "MALIEV-Co-Ltd/Legacy.Maliev.ServiceDefaults",
                ["ref"] = "ecb05cbbd68717e415f69df2ac488c1d323b1da3",
                ["path"] = ".dependencies/Legacy.Maliev.ServiceDefaults",
                ["persist-credentials"] = "false",
            });
        ValidateStep(
            steps.Children[2],
            CheckoutAction,
            new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["repository"] = "MALIEV-Co-Ltd/Legacy.Maliev.CompatibilityContracts",
                ["ref"] = "78e48ffc4ee000df0510cba5e7c7a3c4c4d539d7",
                ["path"] = ".dependencies/Legacy.Maliev.CompatibilityContracts",
                ["persist-credentials"] = "false",
            });
        ValidateStep(
            steps.Children[3],
            SharedValidationAction,
            new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["solution"] = "Legacy.Maliev.ProcurementService.slnx",
                ["use-local-maliev-dependencies"] = "true",
            });
    }

    private static void ValidateFocusedWorkflowGroup(YamlSequenceNode steps)
    {
        if (steps.Children.Count != 24)
            throw new InvalidOperationException("Primary validation must retain the mandatory focused workflow group.");
        ValidateStep(steps.Children[3], "actions/setup-dotnet@a98b56852c35b8e3190ac28c8c2271da59106c68",
            new Dictionary<string, string>(StringComparer.Ordinal) { ["dotnet-version"] = "10.0.x" });
        RequireScalarValue(RequireMapping(steps.Children[3], "focused SDK"), "name", "Set up SDK for mandatory focused workflow checks");
        var build = RequireMapping(steps.Children[4], "focused build");
        RequireStepKeys(build, "name", "timeout-minutes", "run");
        RequireScalarValue(build, "name", "Build before mandatory focused workflow checks");
        RequireScalarValue(build, "timeout-minutes", "5");
        RequireCommands(build, "export GITHUB_ACTIONS=false\n"
            + "python3 -B scripts/verify-procurement-fixture-containment.py --source-admission\n"
            + "dotnet restore Legacy.Maliev.ProcurementService.slnx -p:UseLocalMalievDependencies=true\n"
            + "dotnet build Legacy.Maliev.ProcurementService.slnx --configuration Release --no-restore -warnaserror -p:UseLocalMalievDependencies=true");
        var test = RequireMapping(steps.Children[5], "focused tests");
        RequireStepKeys(test, "name", "timeout-minutes", "env", "run");
        RequireScalarValue(test, "name", "Execute mandatory focused workflow checks");
        RequireScalarValue(test, "timeout-minutes", "2");
        var testEnv = RequireMapping(test, "env");
        RequireStepKeys(testEnv, "VSTestResultsDirectory");
        RequireScalarValue(testEnv, "VSTestResultsDirectory", "${{ github.workspace }}/focused-workflow-results");
        RequireCommands(test, "export GITHUB_ACTIONS=false\n"
            + "dotnet test Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj --configuration Release --no-build --no-restore -p:UseLocalMalievDependencies=true --filter \"FullyQualifiedName~ActualAuthProgramJoin|FullyQualifiedName~ReviewedImagePreload\"");
        var gate = RequireMapping(steps.Children[6], "focused gate");
        RequireStepKeys(gate, "name", "if", "run");
        RequireScalarValue(gate, "name", "Require every focused workflow execution");
        RequireScalarValue(gate, "if", "always()");
        RequireCommands(gate, "python3 -B -m unittest discover -s scripts -p test_focused_workflow_results.py\n"
            + "python3 -B scripts/verify-focused-workflow-results.py focused-workflow-results");
        var evidence = RequireMapping(steps.Children[7], "focused custody");
        RequireStepKeys(evidence, "name", "if", "uses", "with");
        RequireScalarValue(evidence, "name", "Preserve focused workflow evidence");
        RequireScalarValue(evidence, "if", "always()");
        RequireScalarValue(evidence, "uses", "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02");
        var inputs = RequireMapping(evidence, "with");
        RequireStepKeys(inputs, "name", "path", "if-no-files-found", "retention-days");
        RequireScalarValue(inputs, "name", "procurement-focused-workflow-${{ github.sha }}");
        RequireScalarValue(inputs, "path", "focused-workflow-results");
        RequireScalarValue(inputs, "if-no-files-found", "warn");
        RequireScalarValue(inputs, "retention-days", "7");
        ValidateStartupJournalGroup(steps);
        ValidateOwnerCorrelationGroup(steps);
        ValidateDiagnosticFocusedGroup(steps);
    }

    private static void ValidateStartupJournalGroup(YamlSequenceNode steps)
    {
        var test = RequireMapping(steps.Children[8], "startup journal tests");
        RequireStepKeys(test, "name", "timeout-minutes", "env", "run");
        RequireScalarValue(test, "name", "Execute startup journal regressions");
        RequireScalarValue(test, "timeout-minutes", "2");
        var environment = RequireMapping(test, "env");
        RequireStepKeys(environment, "VSTestResultsDirectory");
        RequireScalarValue(environment, "VSTestResultsDirectory", "${{ github.workspace }}/startup-journal-results");
        RequireCommands(test, "export GITHUB_ACTIONS=false\n"
            + "dotnet test Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj --configuration Release --no-build --no-restore -p:UseLocalMalievDependencies=true --filter \"FullyQualifiedName~ProcurementFixtureStartupJournalTests\" --logger \"trx;LogFileName=startup-journal.trx\" --results-directory startup-journal-results");
        var gate = RequireMapping(steps.Children[9], "startup journal gate");
        RequireStepKeys(gate, "name", "if", "run");
        RequireScalarValue(gate, "name", "Require every startup journal execution");
        RequireScalarValue(gate, "if", "always()");
        RequireCommands(gate, "python3 -B -m unittest discover -s scripts -p test_startup_journal_results.py\n"
            + "python3 -B -O -m unittest discover -s scripts -p test_startup_journal_results.py\n"
            + "python3 -B scripts/verify-startup-journal-results.py startup-journal-results");
        var evidence = RequireMapping(steps.Children[10], "startup journal custody");
        RequireStepKeys(evidence, "name", "if", "uses", "with");
        RequireScalarValue(evidence, "name", "Preserve startup journal evidence");
        RequireScalarValue(evidence, "if", "always()");
        RequireScalarValue(evidence, "uses", "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02");
        var inputs = RequireMapping(evidence, "with");
        RequireStepKeys(inputs, "name", "path", "if-no-files-found", "retention-days");
        RequireScalarValue(inputs, "name", "procurement-startup-journal-${{ github.sha }}");
        RequireScalarValue(inputs, "path", "startup-journal-results");
        RequireScalarValue(inputs, "if-no-files-found", "warn");
        RequireScalarValue(inputs, "retention-days", "7");
    }

    private static void ValidateOwnerCorrelationGroup(YamlSequenceNode steps)
    {
        var test = RequireMapping(steps.Children[11], "owner correlation tests");
        RequireStepKeys(test, "name", "timeout-minutes", "env", "run");
        RequireScalarValue(test, "name", "Execute owner correlation regressions");
        RequireScalarValue(test, "timeout-minutes", "2");
        var environment = RequireMapping(test, "env");
        RequireStepKeys(environment, "VSTestResultsDirectory");
        RequireScalarValue(environment, "VSTestResultsDirectory", "${{ github.workspace }}/owner-correlation-results");
        RequireCommands(test, "export GITHUB_ACTIONS=false\n"
            + "dotnet test Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj --configuration Release --no-build --no-restore -p:UseLocalMalievDependencies=true --filter \"FullyQualifiedName~ProcurementFixtureOwnerCorrelationTests\" --logger \"trx;LogFileName=owner-correlation.trx\" --results-directory owner-correlation-results");
        var gate = RequireMapping(steps.Children[12], "owner correlation gate");
        RequireStepKeys(gate, "name", "timeout-minutes", "if", "run");
        RequireScalarValue(gate, "timeout-minutes", "1");
        RequireScalarValue(gate, "name", "Require every owner correlation execution");
        RequireScalarValue(gate, "if", "always()");
        RequireCommands(gate, "python3 -B -m unittest discover -s scripts -p test_owner_correlation_results.py\n"
            + "python3 -B -O -m unittest discover -s scripts -p test_owner_correlation_results.py\n"
            + "python3 -B scripts/verify-owner-correlation-results.py owner-correlation-results");
        var evidence = RequireMapping(steps.Children[13], "owner correlation custody");
        RequireStepKeys(evidence, "name", "timeout-minutes", "if", "uses", "with");
        RequireScalarValue(evidence, "timeout-minutes", "1");
        RequireScalarValue(evidence, "name", "Preserve owner correlation evidence");
        RequireScalarValue(evidence, "if", "always()");
        RequireScalarValue(evidence, "uses", "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02");
        var inputs = RequireMapping(evidence, "with");
        RequireStepKeys(inputs, "name", "path", "if-no-files-found", "retention-days");
        RequireScalarValue(inputs, "name", "procurement-owner-correlation-${{ github.sha }}");
        RequireScalarValue(inputs, "path", "owner-correlation-results");
        RequireScalarValue(inputs, "if-no-files-found", "warn");
        RequireScalarValue(inputs, "retention-days", "7");
    }

    private static void ValidateDiagnosticFocusedGroup(YamlSequenceNode steps)
    {
        var diagnosticStep14 = RequireMapping(steps.Children[14], "diagnostic focused contract");
        RequireStepKeys(diagnosticStep14, "name", "timeout-minutes", "run");
        RequireScalarValue(diagnosticStep14, "name", "Require diagnostic focused source enrollment");
        RequireScalarValue(diagnosticStep14, "timeout-minutes", "1");
        RequireCommands(diagnosticStep14, "python3 -B scripts/verify-diagnostic-focused-results.py --source-contract\npython3 -B -m unittest discover -s scripts -p test_diagnostic_focused_results.py\npython3 -B -O -m unittest discover -s scripts -p test_diagnostic_focused_results.py");
        var diagnosticStep15 = RequireMapping(steps.Children[15], "diagnostic focused contract");
        RequireStepKeys(diagnosticStep15, "name", "timeout-minutes", "env", "run");
        RequireScalarValue(diagnosticStep15, "name", "Execute diagnostic focused regressions");
        RequireScalarValue(diagnosticStep15, "timeout-minutes", "2");
        var diagnosticStep15Env = RequireMapping(diagnosticStep15, "env");
        RequireStepKeys(diagnosticStep15Env, "VSTestResultsDirectory");
        RequireScalarValue(diagnosticStep15Env, "VSTestResultsDirectory", "${{ github.workspace }}/diagnostic-focused-results");
        RequireCommands(diagnosticStep15, "export GITHUB_ACTIONS=false\ndotnet test Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj --configuration Release --no-build --no-restore -p:UseLocalMalievDependencies=true --filter \"FullyQualifiedName~ProcurementDurableDiagnosticPolicyTests\" --logger \"trx;LogFileName=diagnostic-focused.trx\" --results-directory diagnostic-focused-results");
        var diagnosticStep16 = RequireMapping(steps.Children[16], "diagnostic focused contract");
        RequireStepKeys(diagnosticStep16, "name", "timeout-minutes", "if", "run");
        RequireScalarValue(diagnosticStep16, "name", "Require every diagnostic focused execution");
        RequireScalarValue(diagnosticStep16, "timeout-minutes", "1");
        RequireScalarValue(diagnosticStep16, "if", "always()");
        RequireCommands(diagnosticStep16, "python3 -B scripts/verify-diagnostic-focused-results.py diagnostic-focused-results diagnostic");
        var diagnosticStep17 = RequireMapping(steps.Children[17], "diagnostic focused contract");
        RequireStepKeys(diagnosticStep17, "name", "timeout-minutes", "if", "uses", "with");
        RequireScalarValue(diagnosticStep17, "name", "Preserve diagnostic focused evidence");
        RequireScalarValue(diagnosticStep17, "timeout-minutes", "1");
        RequireScalarValue(diagnosticStep17, "if", "always()");
        RequireScalarValue(diagnosticStep17, "uses", "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02");
        var diagnosticStep17With = RequireMapping(diagnosticStep17, "with");
        RequireStepKeys(diagnosticStep17With, "name", "path", "if-no-files-found", "retention-days");
        RequireScalarValue(diagnosticStep17With, "name", "procurement-diagnostic-focused-${{ github.sha }}");
        RequireScalarValue(diagnosticStep17With, "path", "diagnostic-focused-results");
        RequireScalarValue(diagnosticStep17With, "if-no-files-found", "warn");
        RequireScalarValue(diagnosticStep17With, "retention-days", "7");
        var diagnosticStep18 = RequireMapping(steps.Children[18], "diagnostic focused contract");
        RequireStepKeys(diagnosticStep18, "name", "timeout-minutes", "env", "run");
        RequireScalarValue(diagnosticStep18, "name", "Execute durable focused regressions");
        RequireScalarValue(diagnosticStep18, "timeout-minutes", "5");
        var diagnosticStep18Env = RequireMapping(diagnosticStep18, "env");
        RequireStepKeys(diagnosticStep18Env, "VSTestResultsDirectory");
        RequireScalarValue(diagnosticStep18Env, "VSTestResultsDirectory", "${{ github.workspace }}/durable-focused-results");
        RequireCommands(diagnosticStep18, "export GITHUB_ACTIONS=false\ndotnet test Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj --configuration Release --no-build --no-restore -p:UseLocalMalievDependencies=true --filter \"FullyQualifiedName~ProcurementDurableCreateTests|FullyQualifiedName~ProcurementDurableChildCreateTests\" --logger \"trx;LogFileName=durable-focused.trx\" --results-directory durable-focused-results");
        var diagnosticStep19 = RequireMapping(steps.Children[19], "diagnostic focused contract");
        RequireStepKeys(diagnosticStep19, "name", "timeout-minutes", "if", "run");
        RequireScalarValue(diagnosticStep19, "name", "Require every durable focused execution");
        RequireScalarValue(diagnosticStep19, "timeout-minutes", "1");
        RequireScalarValue(diagnosticStep19, "if", "always()");
        RequireCommands(diagnosticStep19, "python3 -B scripts/verify-diagnostic-focused-results.py durable-focused-results durable");
        var diagnosticStep20 = RequireMapping(steps.Children[20], "diagnostic focused contract");
        RequireStepKeys(diagnosticStep20, "name", "timeout-minutes", "if", "uses", "with");
        RequireScalarValue(diagnosticStep20, "name", "Preserve durable focused evidence");
        RequireScalarValue(diagnosticStep20, "timeout-minutes", "1");
        RequireScalarValue(diagnosticStep20, "if", "always()");
        RequireScalarValue(diagnosticStep20, "uses", "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02");
        var diagnosticStep20With = RequireMapping(diagnosticStep20, "with");
        RequireStepKeys(diagnosticStep20With, "name", "path", "if-no-files-found", "retention-days");
        RequireScalarValue(diagnosticStep20With, "name", "procurement-durable-focused-${{ github.sha }}");
        RequireScalarValue(diagnosticStep20With, "path", "durable-focused-results");
        RequireScalarValue(diagnosticStep20With, "if-no-files-found", "warn");
        RequireScalarValue(diagnosticStep20With, "retention-days", "7");
    }

    private static void RequireCommands(YamlMappingNode step, string commands)
    {
        var actual = RequireScalar(GetRequired(step, "run")).Replace("\r\n", "\n", StringComparison.Ordinal).TrimEnd('\n');
        if (actual != commands)
            throw new InvalidOperationException("Mandatory focused commands must remain exact and ordered.");
    }

    internal static void ValidateImagePreloadGroup(YamlNode preloadNode, YamlNode cleanupNode, YamlNode custodyNode)
    {
        var preload = RequireMapping(preloadNode, "reviewed image preload");
        RequireStepKeys(preload, "name", "timeout-minutes", "run");
        RequireScalarValue(preload, "name", "Preload exact official PostgreSQL images");
        RequireScalarValue(preload, "timeout-minutes", "5");
        const string commands = "python3 -B scripts/ci-postgres-preload/test_preload_official_postgres.py\n"
            + "python3 -B -O scripts/ci-postgres-preload/test_preload_official_postgres.py\n"
            + "python3 -B scripts/ci-postgres-preload/preload_official_postgres.py";
        var actualCommands = RequireScalar(GetRequired(preload, "run")).Replace("\r\n", "\n", StringComparison.Ordinal).TrimEnd('\n');
        if (actualCommands != commands)
            throw new InvalidOperationException("Image preload must retain exactly the normal and optimized controls and reviewed command.");

        var cleanup = RequireMapping(cleanupNode, "reviewed image cleanup");
        RequireStepKeys(cleanup, "name", "if", "timeout-minutes", "run");
        RequireScalarValue(cleanup, "name", "Release owned image preload tags");
        RequireScalarValue(cleanup, "if", "always()");
        RequireScalarValue(cleanup, "timeout-minutes", "2");
        RequireScalarValue(cleanup, "run", "python3 -B scripts/ci-postgres-preload/preload_official_postgres.py cleanup");

        var custody = RequireMapping(custodyNode, "reviewed image custody evidence");
        RequireStepKeys(custody, "name", "if", "uses", "with");
        RequireScalarValue(custody, "name", "Preserve image custody evidence");
        RequireScalarValue(custody, "if", "always()");
        RequireScalarValue(custody, "uses", "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02");
        var inputs = RequireMapping(custody, "with");
        RequireStepKeys(inputs, "name", "path", "if-no-files-found", "retention-days");
        RequireScalarValue(inputs, "name", "postgres-preload-${{ github.job }}-${{ github.run_id }}-${{ github.run_attempt }}");
        RequireScalarValue(inputs, "path", "${{ runner.temp }}/procurement-postgres-preload.json");
        RequireScalarValue(inputs, "if-no-files-found", "warn");
        RequireScalarValue(inputs, "retention-days", "7");
    }

    private static void RequireStepKeys(YamlMappingNode step, params string[] expected)
    {
        var actual = step.Children.Keys.Select(RequireScalar).ToHashSet(StringComparer.Ordinal);
        if (!actual.SetEquals(expected))
            throw new InvalidOperationException("Reviewed image preload steps must retain only their exact declared properties.");
    }

    private static IReadOnlyList<string> RequireExactReadOnlyPermissions(YamlMappingNode permissions, string scope)
    {
        if (permissions.Children.Count != 1)
        {
            throw new InvalidOperationException($"{scope} permissions must contain only contents: read.");
        }

        RequireScalarValue(permissions, "contents", "read");
        return ["contents:read"];
    }

    private static void ValidateStep(
        YamlNode node,
        string expectedAction,
        IReadOnlyDictionary<string, string> expectedInputs)
    {
        var step = RequireMapping(node, "workflow step");
        var allowedKeys = new HashSet<string>(["name", "uses", "with"], StringComparer.Ordinal);

        var actualKeys = step.Children.Keys.Select(RequireScalar).ToHashSet(StringComparer.Ordinal);
        if (!actualKeys.SetEquals(allowedKeys))
        {
            throw new InvalidOperationException("Each workflow step must contain exactly name, uses, and with.");
        }

        var name = RequireScalar(GetRequired(step, "name"));
        if (string.IsNullOrWhiteSpace(name))
        {
            throw new InvalidOperationException("Workflow step name must not be empty.");
        }

        RequireScalarValue(step, "uses", expectedAction);
        var inputs = RequireMapping(step, "with");
        if (inputs.Children.Count != expectedInputs.Count)
        {
            throw new InvalidOperationException($"Action {expectedAction} has an unexpected input count.");
        }

        foreach (var expectedInput in expectedInputs)
        {
            RequireScalarValue(inputs, expectedInput.Key, expectedInput.Value);
        }

        var environment = GetOptional(step, "env");
        if (environment is not null)
        {
            throw new InvalidOperationException("Workflow action steps must not override reserved environment variables.");
        }

        if (expectedInputs.ContainsKey("use-local-maliev-dependencies"))
        {
            var useLocalDependencies = GetRequired(inputs, "use-local-maliev-dependencies") as YamlScalarNode;
            if (useLocalDependencies?.Style != ScalarStyle.SingleQuoted)
            {
                throw new InvalidOperationException("use-local-maliev-dependencies must use the single-quoted string value 'true'.");
            }
        }
    }

    private static void RejectDuplicatedValidationActionsAndCommands(YamlSequenceNode steps)
    {
        foreach (var stepNode in steps.Children.OfType<YamlMappingNode>())
        {
            if (GetOptional(stepNode, "uses") is YamlScalarNode usesNode)
            {
                var action = usesNode.Value ?? string.Empty;
                if (action.StartsWith("actions/setup-dotnet@", StringComparison.OrdinalIgnoreCase)
                    || action.StartsWith("actions/cache@", StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException($"Caller duplicates shared action {action}.");
            }
            if (GetOptional(stepNode, "run") is YamlScalarNode runNode)
                RejectDuplicatedDotNetCommand(runNode.Value ?? string.Empty);
        }
    }

    private static void RejectDuplicatedDotNetCommand(string command)
    {
        var tokens = command
            .Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(token => token.Trim('"', '\'', ';', '&', '|').ToLowerInvariant())
            .Where(token => token.Length > 0)
            .ToArray();

        for (var index = 0; index < tokens.Length - 1; index++)
        {
            if (!string.Equals(tokens[index], "dotnet", StringComparison.Ordinal))
            {
                continue;
            }

            var verb = tokens[index + 1];
            if (verb is "restore" or "build" or "test" or "format" or "list"
                || tokens[(index + 1)..].Any(token => token is "audit" or "--vulnerable"))
            {
                throw new InvalidOperationException($"Caller duplicates shared dotnet validation command: {verb}.");
            }
        }
    }

    private static YamlMappingNode RequireMapping(YamlMappingNode parent, string key) =>
        RequireMapping(GetRequired(parent, key), key);

    private static YamlMappingNode RequireMapping(YamlNode node, string description)
    {
        return node as YamlMappingNode
            ?? throw new InvalidOperationException($"{description} must be a mapping.");
    }

    private static YamlSequenceNode RequireSequence(YamlMappingNode parent, string key)
    {
        return GetRequired(parent, key) as YamlSequenceNode
            ?? throw new InvalidOperationException($"{key} must be a sequence.");
    }

    private static void RequireScalarValue(YamlMappingNode parent, string key, string expected)
    {
        var actual = RequireScalar(GetRequired(parent, key));
        if (!string.Equals(actual, expected, StringComparison.Ordinal))
        {
            throw new InvalidOperationException($"{key} must equal '{expected}', but was '{actual}'.");
        }
    }

    private static string RequireScalar(YamlNode node)
    {
        return (node as YamlScalarNode)?.Value
            ?? throw new InvalidOperationException("Expected a scalar YAML value.");
    }

    private static YamlNode GetRequired(YamlMappingNode parent, string key)
    {
        return GetOptional(parent, key)
            ?? throw new InvalidOperationException($"Missing required YAML key '{key}'.");
    }

    private static YamlNode? GetOptional(YamlMappingNode parent, string key)
    {
        foreach (var child in parent.Children)
        {
            if (child.Key is YamlScalarNode scalar && string.Equals(scalar.Value, key, StringComparison.Ordinal))
            {
                return child.Value;
            }
        }

        return null;
    }

    [GeneratedRegex(@"\$\{\{\s*secrets\s*(?:\.|\[)", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)]
    private static partial Regex SecretExpression();
}
